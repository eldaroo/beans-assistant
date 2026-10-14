"""Produccion module integration (spec 003 M3): real data, real registry.

Seeds production for the tenant, then builds the status home through the REAL
module registry and asserts the Produccion tile renders units-versus-target and
that an overdue arrival raises an attention item (AC1 for the new module plus the
arrival-cadence signal T-011). Mirrors test_costos_module.py: the provider
tenant_scope is stubbed to a no-op because populated_db already binds the test DB.
"""
from contextlib import contextmanager

import pytest

import database
from backend.modules import home_service, registry


@contextmanager
def _noop_scope(_phone):
    yield


@pytest.fixture
def produccion_env(populated_db, monkeypatch):
    from backend.modules.providers import (
        caja_module,
        costos_module,
        produccion_module,
        stock_module,
        ventas_module,
    )

    for mod in (stock_module, caja_module, ventas_module, costos_module, produccion_module):
        monkeypatch.setattr(mod, "tenant_scope", _noop_scope)
    monkeypatch.setattr("backend.cache.REDIS_ENABLED", False)

    with database.get_conn() as conn:
        # Latest week 240/300 in Colombia with a past-due expected arrival.
        conn.execute(
            "INSERT INTO production_records (country, period_week, units_produced, units_target, "
            "expected_next_at, recorded_at) VALUES ('Colombia', '2026-W42', 240, 300, '2000-01-01', '2026-10-13')"
        )
    return {}


def test_produccion_tile_shows_units_vs_target(produccion_env):
    view = home_service.build_home("+100")

    by_id = {t.module_id: t for t in view.tiles}
    assert "produccion" in by_id, "the Produccion module must have a tile once registered (AC1)"
    tile = by_id["produccion"]
    assert tile.status == "ok"
    assert tile.value == "240 u"
    assert "meta 300 u" in (tile.trend or "")
    assert "80%" in (tile.trend or "")


def test_produccion_overdue_arrival_raises_attention(produccion_env):
    view = home_service.build_home("+100")

    items = [a for a in view.attention if a.module_id == "produccion"]
    assert items, "an overdue expected arrival must raise an attention item"
    assert any("atrasada" in a.text.lower() for a in items)


def test_produccion_module_registered_and_route_present():
    assert "produccion" in {m.id for m in registry.all_modules()}

    from backend.app import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/produccion/{phone}" in paths
