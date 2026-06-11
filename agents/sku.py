"""
Pure SKU composition and within-batch deduplication.

Dependency-free (no DB, no LLM) so it is unit-testable in isolation and so the
resolver and the database batch helpers share one implementation. Spec D-004 /
T-006 / T-007:

- compose_base_sku retains discriminating tokens (colors and sizes, including
  single-letter sizes like S/M/L) so variants of one base do not collapse to
  the same SKU. This is the direct fix for the screenshot collision where
  "Medias Multicolor Talle S/M/L" all produced BC-PROD-MEDIAS-MULTICOLOR.
- dedup_skus makes a list of SKUs unique against its in-flight siblings,
  suffixing -2, -3 on residual collision, so a single batch never inserts two
  identical SKUs even before any row is committed.
"""
from __future__ import annotations

from typing import List

from agents.attributes import (
    SIZE_KEYWORDS,
    is_discriminator,
    is_size,
    normalize_token,
)

# Product type words -> SKU type token. Types only, never colors.
_TYPE_MAPPING = {
    "pulsera": "PULS", "pulseras": "PULS",
    "bracelet": "PULS", "bracelets": "PULS",
    "llavero": "LLAV", "llaveros": "LLAV",
    "keychain": "LLAV", "keychains": "LLAV",
}

# Filler words that add nothing to a SKU.
_SKIP_WORDS = {
    "de", "del", "la", "las", "el", "los",
    "granos", "cafe", "coffee", "bean", "beans",
    "con", "y", "e", "and", "a",
}


def compose_base_sku(name: str) -> str:
    """Build the base SKU for a product name, retaining discriminators.

    Format: BC-{TYPE}-{up to 2 plain descriptors}-{all discriminator tokens}.
    Discriminators (colors and sizes) are always kept, including single-letter
    sizes, because they are exactly what makes a variant distinct. Plain
    descriptors keep the prior first-two behavior so existing single-variant
    SKUs do not shift.
    """
    words = normalize_token(name).split()

    product_type = None
    plain: List[str] = []
    disc: List[str] = []

    for word in words:
        if word in SIZE_KEYWORDS:
            # The literal keyword "talle" is not itself a descriptor.
            continue
        if word in _TYPE_MAPPING and product_type is None:
            product_type = _TYPE_MAPPING[word]
            continue
        if word in _SKIP_WORDS:
            continue
        if is_discriminator(word):
            disc.append(word.upper())
            continue
        # Plain descriptor: keep, but drop bare single letters that are not
        # sizes (a stray "x" adds nothing; a size letter was caught above).
        if len(word) > 1 and not is_size(word):
            plain.append(word.upper())

    if product_type is None:
        product_type = "PROD"

    parts = [p[:10] for p in plain[:2]] + [d[:10] for d in disc]
    if parts:
        return f"BC-{product_type}-" + "-".join(parts)
    return f"BC-{product_type}-STD"


def dedup_skus(skus: List[str]) -> List[str]:
    """Make a list of SKUs unique against its in-flight siblings.

    Order-preserving. The first occurrence keeps its SKU; each later collision
    gets the lowest free -N suffix (-2, -3, ...). Pure: knows nothing about the
    database. The database layer composes this with a committed-row check.
    """
    seen = set()
    out: List[str] = []
    for sku in skus:
        candidate = sku
        counter = 2
        while candidate in seen:
            candidate = f"{sku}-{counter}"
            counter += 1
        seen.add(candidate)
        out.append(candidate)
    return out
