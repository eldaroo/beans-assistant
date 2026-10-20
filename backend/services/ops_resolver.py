"""Deterministic product resolution for the write-preview path (spec 007 M3, D-042).

The old chat write path (database_pg.register_sale inline lookup, agents/resolver) would
silently take an arbitrary row when a name matched more than one product, and did not
filter inactive products. The auto-post verdict needs the opposite: an honest count of
ACTIVE candidates, so "exactly one" can gate an auto-post and "more than one" routes to a
confirm card instead of guessing (Amelia's single-active-candidate rule). This resolver is
that honest count. It never picks among ambiguous matches.

Runs under the caller's tenant_context (it uses the tenant-scoped db helpers).
"""
from __future__ import annotations

from dataclasses import dataclass

from database_config import fetch_all


@dataclass
class Resolution:
    candidate_count: int
    product: dict | None  # the single active match, or None when 0 or >1
    candidates: list[dict]


def resolve_active_product(product_ref: str) -> Resolution:
    """Resolve a product reference to its ACTIVE candidates.

    An exact (case-insensitive) SKU match is unambiguous and wins as the single
    candidate. Otherwise a name substring match over active products is collected and
    counted; 0 or >1 means not deterministic and ``product`` is None.
    """
    ref = (product_ref or "").strip()
    if not ref:
        return Resolution(candidate_count=0, product=None, candidates=[])

    exact = fetch_all(
        """
        SELECT id, sku, name, unit_price_cents, is_active
        FROM products
        WHERE is_active = TRUE AND LOWER(sku) = LOWER(%s)
        """.replace("%s", _ph()),
        (ref,),
    )
    exact = [dict(r) for r in (exact or [])]
    if len(exact) == 1:
        return Resolution(candidate_count=1, product=exact[0], candidates=exact)

    rows = fetch_all(
        """
        SELECT id, sku, name, unit_price_cents, is_active
        FROM products
        WHERE is_active = TRUE AND LOWER(name) LIKE LOWER(%s)
        ORDER BY name
        """.replace("%s", _ph()),
        ("%" + ref + "%",),
    )
    candidates = [dict(r) for r in (rows or [])]
    count = len(candidates)
    product = candidates[0] if count == 1 else None
    return Resolution(candidate_count=count, product=product, candidates=candidates)


def _ph() -> str:
    """The parameter placeholder for the active DB backend (%s for pg, ? for sqlite).

    database_config.USE_POSTGRES is the single source of truth for which module it
    re-exported."""
    import database_config

    return "%s" if getattr(database_config, "USE_POSTGRES", False) else "?"
