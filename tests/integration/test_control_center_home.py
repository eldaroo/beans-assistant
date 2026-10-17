"""Control Center status-home integration (M1): real data, real registry.

Seeds stock, sales, and expenses into the test database, then builds the home
through the REAL module registry and asserts the three live tiles plus the
low-stock attention item render (AC2). Also asserts the existing surfaces stay
registered and reachable, with the new default route added (AC5).

The providers wrap their service call in ``tenant_scope(phone)`` (request
plumbing that resolves a real tenant). The test DB is bound by the ``populated_db``
fixture that patches ``database.get_conn`` directly, so here ``tenant_scope`` is
stubbed to a no-op; the data path (service -> repository -> SQL -> compute) is
exercised in full.
"""
from contextlib import contextmanager

import pytest

import database
from backend.modules import home_service, registry


@contextmanager
def _noop_scope(_phone):
    yield


@pytest.fixture
def home_env(populated_db, monkeypatch):
    """Seed two stocked products (one low), one paid sale today, one expense."""
    from datetime import date

    from backend.modules.providers import caja_module, stock_module, ventas_module

    # Bind the provider tenant_scope to a no-op; the test DB is already bound.
    for mod in (stock_module, caja_module, ventas_module):
        monkeypatch.setattr(mod, "tenant_scope", _noop_scope)

    # Pin Redis off (as prod does, REDIS_ENABLED=false). Otherwise the cache
    # attempts a 2s-timeout connection to a non-existent Redis per cached call,
    # which can push the stock snapshot past the 3s fail-open deadline on a CI
    # box where the refusal is slow, degrading the tile. Prod never pays this.
    monkeypatch.setattr("backend.cache.REDIS_ENABLED", False)

    with database.get_conn() as conn:
        # Keep exactly two active products so stock totals are deterministic.
        rows = conn.execute("SELECT id FROM products WHERE is_active = 1 ORDER BY id").fetchall()
        ids = [r["id"] for r in rows]
        assert len(ids) >= 2, "fixture must seed at least two products"
        keep_high, keep_low = ids[0], ids[1]
        conn.execute("UPDATE products SET is_active = 0")
        conn.execute("UPDATE products SET is_active = 1 WHERE id IN (?, ?)", (keep_high, keep_low))

        # Stock: one well-stocked product (500), one below threshold (5).
        conn.execute(
            "INSERT INTO stock_movements (product_id, movement_type, quantity, reason) VALUES (?, 'IN', 500, 'seed')",
            (keep_high,),
        )
        conn.execute(
            "INSERT INTO stock_movements (product_id, movement_type, quantity, reason) VALUES (?, 'IN', 5, 'seed')",
            (keep_low,),
        )

        # Sales: one PAID sale today, USD 1900.
        today = date.today().isoformat()
        conn.execute(
            "INSERT INTO sales (sale_number, status, total_amount_cents, created_at, paid_at) "
            "VALUES ('S-1', 'PAID', 190000, ?, ?)",
            (today, today),
        )

        # Expenses: USD 500.
        conn.execute(
            "INSERT INTO expenses (expense_date, category, description, amount_cents) "
            "VALUES (?, 'GENERAL', 'seed', 50000)",
            (today,),
        )

    return {"low_product_id": keep_low}


# ---------------------------------------------------------------- AC2

def test_home_renders_three_live_tiles_from_existing_data(home_env):
    view = home_service.build_home("+100")

    by_id = {t.module_id: t for t in view.tiles}
    assert {"caja", "stock", "ventas"} <= set(by_id), "the three M1 modules must each have a tile"
    assert all(by_id[m].status == "ok" for m in ("caja", "stock", "ventas"))

    # Stock: 500 + 5 = 505 units on hand.
    assert by_id["stock"].value == "505 u"
    # Ventas: the one paid sale today, USD 1900 -> "USD 1.9k".
    assert by_id["ventas"].value == "USD 1.9k"
    # Caja: 1900 revenue - 500 expenses = USD 1.4k net.
    assert by_id["caja"].value == "USD 1.4k"


def test_home_surfaces_low_stock_attention_item(home_env):
    view = home_service.build_home("+100")

    low_items = [a for a in view.attention if a.module_id == "stock"]
    assert low_items, "a low-stock product must raise an attention item (AC2)"
    assert any("bajo" in a.text.lower() for a in low_items)


# ---------------------------------------------------------------- AC5

def test_existing_surfaces_stay_registered_and_reachable():
    """The new default route is added and the existing routes are untouched."""
    from backend.app import app

    paths = {getattr(r, "path", None) for r in app.routes}
    # new default landing
    assert "/home/{phone}" in paths
    # the legacy /tenants dashboard was removed (single-business); API surfaces stay
    assert "/tenants/{phone}" not in paths
    assert "/api/tenants/{phone}/stock" in paths
    assert "/api/tenants/{phone}/expenses" in paths
    assert "/" in paths


def test_registry_registers_the_three_m1_modules():
    ids = {m.id for m in registry.all_modules()}
    assert {"caja", "stock", "ventas"} <= ids
