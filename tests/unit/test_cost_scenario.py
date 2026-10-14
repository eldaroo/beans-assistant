"""COST_SCENARIO read-only recompute tests (spec 003 M5, T-019 / AC10).

AC10: a COST_SCENARIO message returns a recomputed landed cost produced by the
costing service's recompute core reading the stored facts; NO new snapshot (or
any costing) row is written. The detection and parse are deterministic, so the
path is testable without an LLM.
"""
import pytest

from backend.services.costing_service import CostingService
from backend.services import cost_scenario


def _seed_type_two_countries(conn):
    """One bracelet type with a materials-only (parcial) cost in two countries:
    Colombia 100, Costa Rica 300."""
    cur = conn.execute("INSERT INTO products (sku, name, unit_cost_cents, unit_price_cents) VALUES ('BRAC', 'Pulsera café', 0, 50000)")
    pid = cur.lastrowid
    for country, cents in (("Colombia", 100), ("Costa Rica", 300)):
        c = conn.execute("INSERT INTO cost_inputs (name, category, unit) VALUES (?, 'cafe', 'u')", (f"cafe-{country}",)).lastrowid
        conn.execute(
            "INSERT INTO input_purchases (cost_input_id, original_currency, original_amount_cents, fx_rate, usd_amount_cents, quantity) VALUES (?, 'USD', ?, 1.0, ?, 1)",
            (c, cents, cents),
        )
        conn.execute("INSERT INTO bom_lines (product_id, cost_input_id, country, quantity) VALUES (?, ?, ?, 1)", (pid, c, country))
    return pid


# ---------------------------------------------------------------- detection

@pytest.mark.unit
def test_is_scenario_detects_hypotheticals():
    assert cost_scenario.is_scenario("qué pasa si produzco los exhibidores en Colombia")
    assert cost_scenario.is_scenario("escenario: mover la producción a Costa Rica")
    assert cost_scenario.is_scenario("cuanto costaria hacerlo en Armenia")
    # Normal reads/writes are NOT scenarios.
    assert not cost_scenario.is_scenario("cuántos productos tengo")
    assert not cost_scenario.is_scenario("registrar venta de 3 pulseras")


# ---------------------------------------------------------------- recompute

@pytest.mark.unit
@pytest.mark.database
def test_run_scenario_recomputes_from_stored_facts(test_db):
    import database

    with database.get_conn() as conn:
        pid = _seed_type_two_countries(conn)

    svc = CostingService()
    result = cost_scenario.run_scenario(svc, pid, "Colombia", "Costa Rica")
    assert result.baseline_total_cents == 100
    assert result.scenario_total_cents == 300
    assert result.delta_cents == 200
    assert result.moved is True


@pytest.mark.unit
@pytest.mark.database
def test_scenario_writes_nothing(test_db):
    """AC10: recompute reads the stored snapshot and writes NO row."""
    import database

    with database.get_conn() as conn:
        _seed_type_two_countries(conn)

    def _counts():
        with database.get_conn() as conn:
            return {
                t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
                for t in ("landed_cost_snapshots", "input_purchases", "bom_lines",
                          "labor_costs", "packaging_costs", "shipping_lanes",
                          "customs_duties", "indirect_costs", "production_records")
            }

    before = _counts()
    reply = cost_scenario.handle_message("qué pasa si produzco los exhibidores en Costa Rica")
    after = _counts()
    assert reply is not None
    assert before == after, "a scenario recompute must not write any row (AC10)"


# ---------------------------------------------------------------- handler

def _seed_complete_country(conn, pid, country, materials):
    """A COMPLETE landed cost in `country`: materials + 50 labor + 20 packaging +
    40 shipping + 30 customs + 10 indirect (pool 1000 / 100 units)."""
    c = conn.execute("INSERT INTO cost_inputs (name, category, unit) VALUES (?, 'cafe', 'u')", (f"c-{country}",)).lastrowid
    conn.execute("INSERT INTO input_purchases (cost_input_id, original_currency, original_amount_cents, fx_rate, usd_amount_cents, quantity) VALUES (?, 'USD', ?, 1.0, ?, 1)", (c, materials, materials))
    conn.execute("INSERT INTO bom_lines (product_id, cost_input_id, country, quantity) VALUES (?, ?, ?, 1)", (pid, c, country))
    conn.execute("INSERT INTO labor_costs (product_id, country, batch_payment_cents, units_completed) VALUES (?, ?, 5000, 100)", (pid, country))
    conn.execute("INSERT INTO packaging_costs (product_id, country, usd_amount_cents) VALUES (?, ?, 20)", (pid, country))
    conn.execute("INSERT INTO shipping_lanes (product_id, country, usd_amount_cents) VALUES (?, ?, 40)", (pid, country))
    conn.execute("INSERT INTO customs_duties (product_id, country, usd_amount_cents) VALUES (?, ?, 30)", (pid, country))
    conn.execute("INSERT INTO indirect_costs (country, period_month, pool_cents) VALUES (?, '2026-10', 1000)", (country,))
    conn.execute("INSERT INTO production_records (country, period_week, units_produced) VALUES (?, '2026-W40', 100)", (country,))


@pytest.mark.unit
@pytest.mark.database
def test_handle_message_states_direction_only_when_both_complete(test_db):
    """With both countries' costs complete, the reply names the precise sube/baja."""
    import database

    with database.get_conn() as conn:
        pid = conn.execute("INSERT INTO products (sku, name, unit_cost_cents) VALUES ('BRACC','Pulsera café',0)").lastrowid
        _seed_complete_country(conn, pid, "Colombia", materials=100)     # total 250
        _seed_complete_country(conn, pid, "Costa Rica", materials=300)   # total 450

    reply = cost_scenario.handle_message("qué pasa si produzco en Costa Rica")
    assert reply is not None
    assert "Costa Rica" in reply
    assert "no cambié nada" in reply
    assert "sube USD 2.00" in reply   # 450 - 250 = 200 cents


@pytest.mark.unit
@pytest.mark.database
def test_handle_message_suppresses_direction_when_partial(test_db):
    """With a partial side, the reply gives both figures as floors and does NOT
    assert a precise sube/baja (no false-precise delta)."""
    import database

    with database.get_conn() as conn:
        _seed_type_two_countries(conn)  # materials-only, both parcial

    reply = cost_scenario.handle_message("qué pasa si produzco en Costa Rica")
    assert reply is not None
    assert "no cambié nada" in reply
    assert "sube USD" not in reply and "baja USD" not in reply
    assert "no puedo comparar con precisión" in reply


@pytest.mark.unit
def test_handle_message_returns_none_for_non_scenario():
    assert cost_scenario.handle_message("cuántos productos tengo") is None


@pytest.mark.unit
@pytest.mark.database
def test_handle_message_falls_through_when_no_country(test_db):
    """A scenario trigger with no country named is NOT claimed by the cost path;
    it returns None so the normal pipeline handles it (no hijack)."""
    import database

    with database.get_conn() as conn:
        _seed_type_two_countries(conn)

    assert cost_scenario.handle_message("qué pasa si cambio la producción") is None
    assert cost_scenario.handle_message("cuánto costaría contratar a alguien") is None
