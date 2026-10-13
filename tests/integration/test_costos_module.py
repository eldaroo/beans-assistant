"""Costos module integration (spec 003 M2): real data, real registry.

Seeds costing data for the lead bracelet type, then builds the status home through
the REAL module registry and asserts the Costos tile renders the landed cost with
its completeness state and that a pending component raises an attention item (AC1
for the new module plus the costing honesty treatment). Mirrors
test_control_center_home.py: the provider tenant_scope is stubbed to a no-op
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
def costos_env(populated_db, monkeypatch):
    from backend.modules.providers import caja_module, costos_module, stock_module, ventas_module

    for mod in (stock_module, caja_module, ventas_module, costos_module):
        monkeypatch.setattr(mod, "tenant_scope", _noop_scope)
    monkeypatch.setattr("backend.cache.REDIS_ENABLED", False)

    country = "Colombia"
    with database.get_conn() as conn:
        row = conn.execute("SELECT id FROM products WHERE is_active = 1 ORDER BY id").fetchone()
        product_id = row["id"]
        cur = conn.execute("INSERT INTO cost_inputs (name, category, unit) VALUES ('cafe','material','u')")
        cafe = cur.lastrowid
        # cafe: 200 usd-cents for 1 unit -> 200 c/u; bom qty 1 -> materials 200
        conn.execute(
            "INSERT INTO input_purchases (cost_input_id, original_currency, original_amount_cents, "
            "fx_rate, usd_amount_cents, quantity) VALUES (?, 'USD', 200, 1.0, 200, 1)",
            (cafe,),
        )
        conn.execute(
            "INSERT INTO bom_lines (product_id, cost_input_id, country, quantity) VALUES (?, ?, ?, 1)",
            (product_id, cafe, country),
        )
        conn.execute(
            "INSERT INTO labor_costs (product_id, country, batch_payment_cents, units_completed) VALUES (?, ?, 900, 10)",
            (product_id, country),
        )
        conn.execute(
            "INSERT INTO packaging_costs (product_id, country, usd_amount_cents) VALUES (?, ?, 28)",
            (product_id, country),
        )
        # shipping, customs, indirect missing -> those components stay pending
    return {"product_id": product_id, "country": country}


def test_costos_tile_shows_landed_cost_with_completeness(costos_env):
    view = home_service.build_home("+100")

    by_id = {t.module_id: t for t in view.tiles}
    assert "costos" in by_id, "the Costos module must have a tile once registered (AC1)"
    tile = by_id["costos"]
    assert tile.status == "ok"
    # materials 200 + labor 90 + packaging 28 = 318 -> USD 3.18, partial (trailing +).
    assert tile.value == "USD 3.18 +"
    assert "parcial" in (tile.trend or "")


def test_costos_pending_component_raises_attention(costos_env):
    view = home_service.build_home("+100")

    costos_items = [a for a in view.attention if a.module_id == "costos"]
    assert costos_items, "a pending cost component must raise an attention item"
    assert any(("falta" in a.text.lower()) for a in costos_items)


def test_costos_module_registered_and_route_present():
    assert "costos" in {m.id for m in registry.all_modules()}

    from backend.app import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/costos/{phone}" in paths
