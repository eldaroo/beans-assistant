"""Stock (Inventario) module: units-on-hand headline + low-stock attention.

One fetch per render (AC-shell / plan risk 2): ``snapshot`` opens a single
tenant scope, reads current stock once, and derives both the tile and the strip
items from that one list.

Note on the mockup's "stock de cafe bajo ... quedan 1.5 semanas": a
weeks-of-cover metric needs a consumption rate the platform does not store until
the production module lands (M3). M1 honestly uses the data it has: units on
hand, and a low-stock signal when a product falls below ``LOW_STOCK_THRESHOLD``.
The threshold is uniform across SKUs in M1 (a velocity-aware, per-product
threshold is the OQ4 setting, tracked for a later milestone).
"""
from __future__ import annotations

from backend.api.tenant_scope import tenant_scope
from backend.modules.formatting import units
from backend.modules.protocol import (
    STATUS_EMPTY,
    STATUS_OK,
    AttentionItem,
    Headline,
    ModuleSnapshot,
    Severity,
)
from backend.services.stock_service import StockService

# Default low-stock threshold in units (OQ4: a sensible starting value, surfaced
# as a per-product setting later). At or below this raises MID; at or below a
# quarter of it, HIGH.
LOW_STOCK_THRESHOLD = 20
# Ceiling on products read for the headline. If a tenant ever exceeds this the
# total is flagged partial rather than silently undercounted.
MAX_PRODUCTS = 2000

# Repointed to the dedicated Stock page (spec 004 S3 / T-007); the low-stock
# attention item drills into /stock/{phone}, not the legacy ?tab=stock bounce.
_ROUTE = "/stock/{phone}"
_service = StockService()


def _qty(i) -> int:
    return int(getattr(i, "stock_qty", 0) or 0)


def compute_snapshot(items) -> ModuleSnapshot:
    """Build the tile + strip from a list of StockCurrentResponse."""
    if not items:
        # No active products yet: a fresh tenant, not a zero count.
        return ModuleSnapshot(
            headline=Headline(value="0 u", trend="sin productos", trend_tone="flat", status=STATUS_EMPTY),
            attention=[],
        )

    # snapshot() fetches MAX_PRODUCTS + 1 so a full page is an exact signal of
    # truncation (not a false "(parcial)" for a tenant with exactly the ceiling).
    partial = len(items) > MAX_PRODUCTS
    if partial:
        items = items[:MAX_PRODUCTS]
    total = sum(_qty(i) for i in items)
    low = sorted((i for i in items if _qty(i) <= LOW_STOCK_THRESHOLD), key=_qty)

    if low:
        trend = f"{len(low)} productos bajos" if len(low) > 1 else "1 producto bajo"
        tone = "warn"
    else:
        trend = "sin faltantes"
        tone = "good"
    if partial:
        trend += " (parcial)"

    value = units(total) + (" +" if partial else "")
    attention = [
        AttentionItem(
            severity=Severity.HIGH if _qty(i) <= LOW_STOCK_THRESHOLD // 4 else Severity.MID,
            text=f"Stock bajo: {getattr(i, 'name', 'producto')} quedan {_qty(i)} u",
            action_label="Reponer",
            route=_ROUTE,
        )
        for i in low
    ]
    return ModuleSnapshot(headline=Headline(value=value, trend=trend, trend_tone=tone, status=STATUS_OK), attention=attention)


def snapshot(phone: str) -> ModuleSnapshot:
    with tenant_scope(phone):
        items = _service.get_current_stock(phone=phone, limit=MAX_PRODUCTS + 1, offset=0)
    return compute_snapshot(items)
