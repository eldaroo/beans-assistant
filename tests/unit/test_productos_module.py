"""Productos module provider tests (spec 004, S2, T-005).

The provider headlines the active product count in one bounded query and fails
open to a degraded tile when it raises. These assert the pure compute_snapshot
count/empty/partial rules (no DB), the registry registration and rail position,
and that a raising provider degrades through the home service rather than
raising into the page (AC2).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.modules import home_service, registry
from backend.modules.protocol import STATUS_DEGRADED, STATUS_EMPTY, STATUS_OK, Module
from backend.modules.providers import productos_module


def _items(n):
    """n stand-in active products; compute_snapshot only reads truthiness/len."""
    return [SimpleNamespace(id=i, name=f"P{i}") for i in range(n)]


def test_empty_tenant_is_zero_not_degraded():
    snap = productos_module.compute_snapshot([])
    assert snap.headline.value == "0"
    assert snap.headline.status == STATUS_EMPTY
    assert snap.headline.trend == "sin productos"
    assert snap.attention == []


def test_count_headlines_the_active_total():
    snap = productos_module.compute_snapshot(_items(4))
    assert snap.headline.value == "4"
    assert snap.headline.status == STATUS_OK
    assert snap.headline.trend == "activos"
    assert snap.attention == []


def test_single_product_is_singular():
    snap = productos_module.compute_snapshot(_items(1))
    assert snap.headline.value == "1"
    assert snap.headline.trend == "activo"


def test_over_ceiling_flags_partial_and_never_undercounts():
    # snapshot() fetches MAX+1; a full+1 page caps the count and marks it partial.
    snap = productos_module.compute_snapshot(_items(productos_module.MAX_PRODUCTS + 1))
    assert snap.headline.value == f"{productos_module.MAX_PRODUCTS} +"
    assert "(parcial)" in snap.headline.trend


def test_exactly_ceiling_is_not_partial():
    snap = productos_module.compute_snapshot(_items(productos_module.MAX_PRODUCTS))
    assert snap.headline.value == f"{productos_module.MAX_PRODUCTS}"
    assert "(parcial)" not in snap.headline.trend


def test_registered_as_eighth_module_between_resultado_and_stock():
    mods = {m.id: m for m in registry.all_modules()}
    assert "productos" in mods
    p = mods["productos"]
    assert p.label == "Productos"
    assert p.route == "/productos/{phone}"
    assert p.rail_group == "Operación"
    # Rail order matches the mockup: Resultado(caja,10) -> Productos(15) -> Stock(20).
    assert mods["caja"].order < p.order < mods["stock"].order


def test_raising_provider_degrades_to_a_dash_not_a_raise():
    """AC2 fail-open: a broken provider renders '—' through the home service's
    degrade path, never raising into the page."""
    def boom(_phone):
        raise RuntimeError("db down")

    broken = Module(id="productos", label="Productos", route="/productos/{phone}", snapshot=boom)
    view = home_service.build_home("+100", modules=[broken])
    tile = next(t for t in view.tiles if t.module_id == "productos")
    assert tile.status == STATUS_DEGRADED
    assert tile.value == "—"
