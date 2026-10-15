"""Productos module: active-product-count headline (spec 004, S2, T-005).

The eighth Control Center module. One fetch per render (plan risk 2 / AC2):
``snapshot`` opens a single tenant scope, reads the active products once, and
headlines the count. The tile carries no attention item in this cohort — the
owner's product work lives on the dedicated Productos page (T-006); the tile is
a count and a door. A broken provider degrades to a dash through the home
service's fail-open path (home_service.build_home catches and renders "—"),
never raising into the page (AC2).
"""
from __future__ import annotations

from backend.api.tenant_scope import tenant_scope
from backend.modules.protocol import (
    STATUS_EMPTY,
    STATUS_OK,
    Headline,
    ModuleSnapshot,
)
from backend.services.products_service import ProductsService

# Ceiling on products read for the headline. If a tenant ever exceeds this the
# count is flagged partial (a trailing "+") rather than silently undercounted —
# the same honesty rule the Stock and Costos tiles use.
MAX_PRODUCTS = 2000

_service = ProductsService()


def compute_snapshot(items) -> ModuleSnapshot:
    """Build the tile from a list of active ProductResponse. Pure, so the count
    and the empty/partial rules are unit-testable without a DB."""
    if not items:
        # No active products yet: a fresh tenant, not a degraded tile.
        return ModuleSnapshot(
            headline=Headline(value="0", trend="sin productos", trend_tone="flat", status=STATUS_EMPTY),
            attention=[],
        )

    # snapshot() fetches MAX_PRODUCTS + 1 so a full page is an exact signal of
    # truncation (not a false "+" for a tenant with exactly the ceiling).
    partial = len(items) > MAX_PRODUCTS
    count = MAX_PRODUCTS if partial else len(items)
    value = f"{count}" + (" +" if partial else "")
    trend = "activos" if count != 1 else "activo"
    if partial:
        trend += " (parcial)"
    return ModuleSnapshot(
        headline=Headline(value=value, trend=trend, trend_tone="flat", status=STATUS_OK),
        attention=[],
    )


def snapshot(phone: str) -> ModuleSnapshot:
    with tenant_scope(phone):
        items = _service.list_products(
            phone=phone, include_inactive=False, limit=MAX_PRODUCTS + 1, offset=0
        )
    return compute_snapshot(items)
