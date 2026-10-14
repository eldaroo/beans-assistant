"""Logistica module integration (spec 003 M4, T-016): real data, real registry.

Seeds a costable bracelet type with a filled shipping lane and a PENDING customs
duty, then builds the status home through the REAL module registry and asserts
the Logistica tile renders and the pending-customs attention item surfaces (AC1
for the new module plus the pending-customs signal T-016 / AC8). Mirrors
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
def logistica_env(populated_db, monkeypatch):
    from backend.modules.providers import (
        caja_module,
        costos_module,
        logistica_module,
        produccion_module,
        stock_module,
        ventas_module,
    )

    for mod in (stock_module, caja_module, ventas_module, costos_module,
                produccion_module, logistica_module):
        monkeypatch.setattr(mod, "tenant_scope", _noop_scope)
    monkeypatch.setattr("backend.cache.REDIS_ENABLED", False)

    with database.get_conn() as conn:
        # A costable lead type with a COMPLETE Colombia landed cost, so the Costos
        # module reports a complete country and stays quiet on the strip, leaving
        # the pending-customs signal from Logistica easy to assert against the cap.
        cur = conn.execute("INSERT INTO cost_inputs (name, category, unit) VALUES ('cafe', 'cafe', 'u')")
        ci = cur.lastrowid
        pid_row = conn.execute("SELECT id FROM products WHERE is_active LIMIT 1").fetchone()
        pid = pid_row["id"]
        conn.execute("INSERT INTO input_purchases (cost_input_id, original_currency, original_amount_cents, fx_rate, usd_amount_cents, quantity) VALUES (?, 'USD', 10000, 1.0, 10000, 1)", (ci,))
        conn.execute("INSERT INTO bom_lines (product_id, cost_input_id, country, quantity) VALUES (?, ?, 'Colombia', 1)", (pid, ci))
        conn.execute("INSERT INTO labor_costs (product_id, country, batch_payment_cents, units_completed) VALUES (?, 'Colombia', 5000, 100)", (pid,))
        conn.execute("INSERT INTO packaging_costs (product_id, country, usd_amount_cents) VALUES (?, 'Colombia', 2000)", (pid,))
        conn.execute("INSERT INTO shipping_lanes (product_id, country, usd_amount_cents) VALUES (?, 'Colombia', 4000)", (pid,))
        conn.execute("INSERT INTO customs_duties (product_id, country, usd_amount_cents) VALUES (?, 'Colombia', 3000)", (pid,))
        conn.execute("INSERT INTO indirect_costs (country, period_month, pool_cents) VALUES ('Colombia', '2026-10', 1000)")
        conn.execute("INSERT INTO production_records (country, period_week, units_produced) VALUES ('Colombia', '2026-W40', 100)")
        # Costa Rica and Armenia-Colombia: shipping filled, customs PENDING -> two
        # pending-customs signals (not shipping), under the per-module and strip cap.
        conn.execute("INSERT INTO shipping_lanes (product_id, country, usd_amount_cents) VALUES (?, 'Costa Rica', 5000)", (pid,))
        conn.execute("INSERT INTO customs_duties (product_id, country, usd_amount_cents) VALUES (?, 'Costa Rica', NULL)", (pid,))
        conn.execute("INSERT INTO shipping_lanes (product_id, country, usd_amount_cents) VALUES (?, 'Armenia-Colombia', 6000)", (pid,))
        conn.execute("INSERT INTO customs_duties (product_id, country, usd_amount_cents) VALUES (?, 'Armenia-Colombia', NULL)", (pid,))
    return {}


def test_logistica_tile_renders(logistica_env):
    view = home_service.build_home("+100")
    by_id = {t.module_id: t for t in view.tiles}
    assert "logistica" in by_id, "the Logistica module must have a tile once registered (AC1)"
    tile = by_id["logistica"]
    assert tile.status == "ok"
    assert tile.value == "USD 70.00"  # cheapest complete lane: Colombia 4000 + 3000


def test_logistica_pending_customs_raises_attention(logistica_env):
    view = home_service.build_home("+100")
    items = [a for a in view.attention if a.module_id == "logistica"]
    assert items, "a pending customs duty must raise an attention item"
    assert any("aduana pendiente" in a.text.lower() for a in items)


def test_logistica_module_registered_and_route_present():
    assert "logistica" in {m.id for m in registry.all_modules()}

    from backend.app import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/logistica/{phone}" in paths
