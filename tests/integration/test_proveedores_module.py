"""Proveedores module integration (spec 003 M5): real data, real registry.

Seeds suppliers (one long overdue on its check-in), then builds the status home
through the REAL module registry and asserts the Proveedores tile renders the
active count and that the overdue supplier raises an attention item (AC1 for the
new module plus the overdue-check-in signal T-018/AC13). Mirrors
test_produccion_module.py: the provider tenant_scope is stubbed to a no-op
because populated_db already binds the test DB.
"""
from contextlib import contextmanager

import pytest

import database
from backend.modules import home_service, registry


@contextmanager
def _noop_scope(_phone):
    yield


@pytest.fixture
def proveedores_env(populated_db, monkeypatch):
    from backend.modules.providers import (
        caja_module,
        costos_module,
        logistica_module,
        produccion_module,
        proveedores_module,
        stock_module,
        ventas_module,
    )

    for mod in (stock_module, caja_module, ventas_module, costos_module,
                produccion_module, logistica_module, proveedores_module):
        monkeypatch.setattr(mod, "tenant_scope", _noop_scope)
    monkeypatch.setattr("backend.cache.REDIS_ENABLED", False)

    with database.get_conn() as conn:
        # A long-overdue supplier (checked in back in January) and a current one.
        conn.execute(
            "INSERT INTO suppliers (name, country, contact, is_active, last_checkin_at) "
            "VALUES ('Café del Valle', 'Colombia', '+57 300', 1, '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO suppliers (name, country, is_active, last_checkin_at) "
            "VALUES ('Maderas Armenia', 'Armenia-Colombia', 1, NULL)"
        )
    return {}


def test_proveedores_tile_shows_count(proveedores_env):
    view = home_service.build_home("+100")
    by_id = {t.module_id: t for t in view.tiles}
    assert "proveedores" in by_id, "the Proveedores module must have a tile once registered (AC1)"
    tile = by_id["proveedores"]
    assert tile.status == "ok"
    assert tile.value == "2"


def test_proveedores_overdue_raises_attention(proveedores_env):
    view = home_service.build_home("+100")
    items = [a for a in view.attention if a.module_id == "proveedores"]
    assert items, "an overdue supplier check-in must raise an attention item"
    assert any("café del valle" in a.text.lower() for a in items)


def test_proveedores_module_registered_and_route_present():
    assert "proveedores" in {m.id for m in registry.all_modules()}

    from backend.app import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/proveedores/{phone}" in paths
