"""The server-computed auto-post verdict (spec 007 M3, D-040 / D-041 / D-042).

"Reversible posts, irreversible asks." A write auto-posts (the client auto-submits
`/chat/confirm` with a loud Undo) ONLY when the APP proves it safe. This module is
that proof. It is pure (no DB, no network, no model) so it is cheap to test and can
never be talked into a yes by tenant text or a hijacked model.

A write may auto-post iff ALL hold:
  (a) reversible set   — operation_type in {REGISTER_SALE, REGISTER_EXPENSE, ADD_STOCK}
  (b) provenance       — every load-bearing numeral in the staged args appears VERBATIM
                         in the operator's own utterance this turn (the wal-ledger
                         `numberTokens` / "no number left behind" invariant, in Python),
                         and the product name (when the op names one) appears too
  (c) determinism      — the product resolved to exactly one active candidate
  (d) within caps      — per-write and per-session caps hold
A bare confirmation turn ("ok", "dale") grounds nothing, so it is never auto (D-041,
Tamir's cross-turn provenance-laundering catch). Provenance is computed here against the
literal utterance — never read from a model field or a tool result (D-042).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# The only operations that may ever auto-post. Everything else (price changes,
# product registration, cancels, deactivation, batch) is confirm-only (D-044, M4).
REVERSIBLE_OPS = frozenset({"REGISTER_SALE", "REGISTER_EXPENSE", "ADD_STOCK"})

# A turn whose entire content (normalized) is one of these is a bare confirmation: it
# carries no new grounded fact, so it can never carry consent for an auto-post.
_BARE_CONFIRMATIONS = frozenset({
    "ok", "oka", "okay", "dale", "si", "sii", "sip", "listo", "hecho", "confirmo",
    "confirmar", "va", "vale", "bueno", "perfecto", "de una", "sisi", "yes", "y", "ya",
})

# A maximal run of digits with optional thousands/decimal separators.
_NUMBER_RE = re.compile(r"\d[\d.,]*\d|\d")


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _parse_one(raw: str):
    """Parse one numeral token to a float, resolving thousands vs decimal separators.

    Locale is ambiguous, so a heuristic (not a dual string form, which collided 1.5 with 15):
    - both '.' and ',' present -> the LAST one is the decimal point, the rest are thousands;
    - one separator appearing once with EXACTLY three trailing digits -> thousands (1.500 = 1500);
      otherwise that single separator is a decimal point (1.5 = 1.5, 12.50 = 12.5);
    - one separator appearing more than once -> thousands (1.500.000 = 1500000);
    - no separator -> the integer.
    Returns None if it does not parse.
    """
    s = raw.strip()
    if not s:
        return None
    has_dot, has_comma = "." in s, "," in s
    try:
        if has_dot and has_comma:
            dec = max(s.rfind("."), s.rfind(","))
            intpart = re.sub(r"[.,]", "", s[:dec])
            frac = re.sub(r"[.,]", "", s[dec + 1:])
            return float(f"{intpart}.{frac}")
        if has_dot or has_comma:
            sep = "." if has_dot else ","
            if s.count(sep) > 1:
                return float(s.replace(sep, ""))
            left, right = s.split(sep)
            if len(right) == 3:  # grouping -> thousands
                return float(left + right)
            return float(left + "." + right)  # decimal
        return float(s)
    except ValueError:
        return None


def parse_numbers(text: str) -> set[float]:
    """Every numeral in ``text`` parsed to its numeric value (thousands/decimal resolved)."""
    out: set[float] = set()
    for m in _NUMBER_RE.finditer(text or ""):
        v = _parse_one(m.group(0))
        if v is not None:
            out.add(v)
    return out


# Back-compat shim: the display strings of the parsed values (some callers/tests want strings).
def number_tokens(text: str) -> set[str]:
    out: set[str] = set()
    for v in parse_numbers(text):
        out.add(str(int(v)) if v == int(v) else str(v))
    return out


def numeral_is_grounded(value, utterance_numbers) -> bool:
    """True iff ``value`` equals (to the cent) a numeral the operator actually said.

    ``utterance_numbers`` may be a set of floats (parse_numbers) or of strings (number_tokens);
    both are accepted. Numeric comparison avoids the scale collision where the separators-stripped
    form of 1.5 ("15") wrongly matched an utterance "15" (council: Tamir/Edut/Amelia)."""
    if value is None:
        return False
    try:
        fval = float(value)
    except (TypeError, ValueError):
        return False
    nums = set()
    for n in (utterance_numbers or set()):
        if isinstance(n, (int, float)):
            nums.add(float(n))
        else:
            v = _parse_one(str(n))
            if v is not None:
                nums.add(v)
    return any(abs(fval - n) < 0.005 for n in nums)


def _token_set(text: str) -> set[str]:
    return set(_strip_accents((text or "").lower()).split())


def is_bare_confirmation(utterance: str) -> bool:
    norm = _strip_accents((utterance or "").strip().lower())
    norm = re.sub(r"[^\w\s]", "", norm).strip()
    return norm in _BARE_CONFIRMATIONS or norm == ""


def product_name_grounded(product_name: str, utterance: str) -> bool:
    """True iff at least one meaningful word of the product name appears in the
    utterance. Accent- and case-insensitive; a one-letter token does not count."""
    if not product_name:
        return True  # op carries no product to ground (e.g. a pure expense)
    utter = _token_set(utterance)
    name_words = [w for w in _token_set(product_name) if len(w) > 2]
    if not name_words:
        name_words = [w for w in _token_set(product_name) if w]
    return any(w in utter for w in name_words)


@dataclass
class Verdict:
    auto: bool
    requires_human_review: bool
    reasons: list[str] = field(default_factory=list)


def compute_verdict(
    *,
    operation_type: str,
    utterance: str,
    grounded_amounts: list,
    product_name: str | None,
    candidate_count: int,
    within_caps: bool = True,
    irreversible: bool = False,
) -> Verdict:
    """Decide auto vs card for one staged write. See module docstring for the rule.

    ``grounded_amounts`` are the load-bearing numerals of the staged op (unit price,
    amount, a quantity greater than one) that MUST each trace to the utterance.
    ``irreversible`` short-circuits to a card (M4 bucket).
    """
    reasons: list[str] = []
    op = (operation_type or "").upper()

    if irreversible:
        reasons.append("irreversible-op")
        return Verdict(auto=False, requires_human_review=True, reasons=reasons)

    reversible = op in REVERSIBLE_OPS
    if not reversible:
        reasons.append(f"not-in-reversible-set:{op}")

    if is_bare_confirmation(utterance):
        reasons.append("bare-confirmation")

    said = parse_numbers(utterance)
    ungrounded = [a for a in grounded_amounts if not numeral_is_grounded(a, said)]
    if ungrounded:
        reasons.append(f"ungrounded-numerals:{ungrounded}")

    if not product_name_grounded(product_name, utterance):
        reasons.append("product-not-in-utterance")

    deterministic = candidate_count == 1
    if candidate_count == 0:
        reasons.append("no-product-match")
    elif candidate_count > 1:
        reasons.append(f"ambiguous-{candidate_count}-candidates")

    if not within_caps:
        reasons.append("over-cap")

    auto = (
        reversible
        and not is_bare_confirmation(utterance)
        and not ungrounded
        and product_name_grounded(product_name, utterance)
        and deterministic
        and within_caps
    )
    return Verdict(auto=auto, requires_human_review=not auto, reasons=reasons)
