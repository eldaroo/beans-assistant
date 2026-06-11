"""
Attribute expander - turns "base noun + coordinated attribute list + shared
price" into a concrete set of products before the resolver runs.

This is the deterministic fan-out the pipeline never had. Per ARCHITECTURE.md
D-001 it lives as its own node between router and resolver, REGISTER_PRODUCT
only, and fails open: any phrasing it does not recognize returns no change and
the existing single-item path handles it. Per D-002 it is pure deterministic
code (no LLM) over the regular grammar of color lists and size lists. Per D-003
the trailing shared price distributes to every expanded sibling in cents.

Dependency-free at module load (no langchain, no DB) so the grammar is
unit-testable in isolation.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from agents.attributes import (
    SIZE_KEYWORDS,
    canonical_size,
    is_color,
    normalize_token,
)

# Operation types the expander serves. Everything else passes through.
EXPANDABLE_OPS = {"REGISTER_PRODUCT", "REGISTER_PRODUCT_WITH_STOCK"}

# Leading verbs / fillers an owner puts before the product phrase.
_LEADING = re.compile(
    r"^\s*(?:y|e|que|,)?\s*"
    r"(?:vendo|vende[r]?|registr[ao]|registrar|registrame|crear|cre[oa]|"
    r"cargar|cargo|carg[aá]me|agregar|agrego|tengo|son|hay|quiero)?\s*",
    flags=re.IGNORECASE,
)

# A price written as a currency-worded amount or a $-prefixed amount.
_PRICE_WORDED = re.compile(
    r"(?:\ba\s+)?\$?\s*(\d+(?:[.,]\d+)?)\s*(?:d[oó]lar(?:es)?|usd|peso(?:s)?)\b",
    flags=re.IGNORECASE,
)
_PRICE_DOLLAR = re.compile(r"\$\s*(\d+(?:[.,]\d+)?)")

# List separators: comma, " y ", " e ".
_SEPARATORS = re.compile(r"\s*,\s*|\s+y\s+|\s+e\s+", flags=re.IGNORECASE)

_CONNECTORS = {"y", "e"}


def _title(text: str) -> str:
    """Capitalize each word without disturbing already-cased acronyms."""
    return " ".join(w[:1].upper() + w[1:] for w in text.split())


def _clean(word: str) -> str:
    return word.strip().strip(",.;:")


def _extract_price(text: str):
    """Return (price_cents_or_None, text_without_price)."""
    for pattern in (_PRICE_WORDED, _PRICE_DOLLAR):
        m = pattern.search(text)
        if m:
            raw = m.group(1).replace(",", ".")
            try:
                cents = int(round(float(raw) * 100))
            except ValueError:
                continue
            text = (text[: m.start()] + " " + text[m.end():]).strip()
            return cents, text
    return None, text


def _expand_sizes(base: str, rest: str, price_cents) -> Optional[List[Dict[str, Any]]]:
    tokens = [_clean(t) for t in _SEPARATORS.split(rest) if _clean(t)]
    if len(tokens) < 2:
        return None
    sizes = [canonical_size(t) for t in tokens]
    if not all(sizes):
        return None
    base_title = _title(base.strip())
    if not base_title:
        return None
    return [
        {"name": f"{base_title} Talle {s}", "unit_price_cents": price_cents}
        for s in sizes
    ]


def _expand_colors(text: str, price_cents) -> Optional[List[Dict[str, Any]]]:
    words = text.split()
    color_idx = [i for i, w in enumerate(words) if is_color(_clean(w))]
    if len(color_idx) < 2:
        return None
    first, last = color_idx[0], color_idx[-1]
    # Everything between the first and last color must be a color or a bare
    # connector; otherwise the run mixes a second noun ("azules y soquetes
    # grises") and is not one base with a color list.
    for i in range(first, last + 1):
        token = normalize_token(_clean(words[i]))
        if i in color_idx or token in _CONNECTORS or token == "":
            continue
        return None
    base = " ".join(words[:first]).strip()
    if not base:
        return None
    base_title = _title(base)
    return [
        {"name": f"{base_title} {_title(_clean(words[i]))}", "unit_price_cents": price_cents}
        for i in color_idx
    ]


def expand_items(phrase: str) -> Optional[List[Dict[str, Any]]]:
    """Expand a single product phrase into a concrete item set, or None.

    Returns a list of {name, unit_price_cents} with at least two members when
    the phrase is a base noun plus a coordinated color or size list, with the
    shared price distributed. Returns None for anything else (single product,
    bare numbers, unknown attributes) so the caller fails open.
    """
    if not phrase:
        return None

    text = _LEADING.sub("", phrase, count=1).strip()
    price_cents, text = _extract_price(text)
    text = text.strip().strip(",.;: ")
    if not text:
        return None

    # Size list takes precedence: the "talle" keyword anchors it unambiguously.
    size_kw = "|".join(sorted(SIZE_KEYWORDS))
    m = re.search(rf"\b(?:{size_kw})\b\s*(.+)$", text, flags=re.IGNORECASE)
    if m:
        base = text[: m.start()]
        sized = _expand_sizes(base, m.group(1), price_cents)
        if sized:
            return sized

    return _expand_colors(text, price_cents)


def create_expander_node() -> Callable[[Any], Dict[str, Any]]:
    """Graph node factory. Runs between router and resolver.

    For an expandable operation, re-reads the raw sub-input and, when it is a
    coordinated variant list, replaces normalized_entities['items'] with the
    expanded concrete set. Fails open: any non-expandable op or unrecognized
    phrasing returns an empty delta and the resolver proceeds unchanged.
    """

    def expand(state: Dict[str, Any]) -> Dict[str, Any]:
        operation_type = state.get("operation_type")
        if operation_type not in EXPANDABLE_OPS:
            return {}

        phrase = state.get("user_input") or ""
        try:
            items = expand_items(phrase)
        except Exception:
            # The expander must never raise into the graph (D-002 fail-open).
            return {}

        if not items or len(items) < 2:
            return {}

        entities = dict(state.get("normalized_entities") or {})
        entities["items"] = items
        # The expanded set is the source of truth; drop a single-product name
        # the router may have extracted so the batch path is taken.
        entities.pop("name", None)

        return {
            "normalized_entities": entities,
            "missing_fields": [],
            "messages": [{
                "role": "assistant",
                "content": f"[Expander] expanded {len(items)} items",
            }],
        }

    return expand
