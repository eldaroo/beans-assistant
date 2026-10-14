"""Costing service tests (spec 003 M2).

Covers:
  - AC8: landed_cost(type, country) = materials (via the BOM) + labor + packaging
    + shipping + customs + prorated indirect; a null shipping/customs line is
    flagged and excluded (never summed as zero); status=parcial with the pending
    components named.
  - AC7: an input purchase stores original_currency, original_amount_cents,
    fx_rate and a derived usd_amount_cents; a correction is a second row and never
    mutates the first (append-only).
  - AC12: a month with zero recorded production renders indirect PENDING, not a
    divide-by-zero.
  - The pure recompute core (the read-only scenario path reused by M5/AC10).
"""
import pytest

from backend.repositories.costing_repository import CostingRepository
from backend.services.costing_service import (
    STATUS_COMPLETE,
    STATUS_PARTIAL,
    CostComponent,
    CostingService,
    recompute,
)


def _seed_cost_input(conn, name):
    cur = conn.execute("INSERT INTO cost_inputs (name, category, unit) VALUES (?, 'material', 'u')", (name,))
    return cur.lastrowid


def _seed_purchase(conn, cost_input_id, usd_cents, quantity):
    conn.execute(
        "INSERT INTO input_purchases (cost_input_id, original_currency, original_amount_cents, "
        "fx_rate, usd_amount_cents, quantity) VALUES (?, 'USD', ?, 1.0, ?, ?)",
        (cost_input_id, usd_cents, usd_cents, quantity),
    )


def _seed_bom(conn, product_id, cost_input_id, country, qty):
    conn.execute(
        "INSERT INTO bom_lines (product_id, cost_input_id, country, quantity) VALUES (?, ?, ?, ?)",
        (product_id, cost_input_id, country, qty),
    )


# ------------------------------------------------------------ pure recompute

@pytest.mark.unit
def test_recompute_sums_filled_and_names_pending():
    comps = [
        CostComponent("materials", "Materiales", 182),
        CostComponent("labor", "Mano de obra", 90),
        CostComponent("packaging", "Empaque", 28),
        CostComponent("shipping", "Envío", None),
        CostComponent("customs", "Aduana", None),
        CostComponent("indirect", "Indirectos", 28),
    ]
    resolved, total, status, pending = recompute(comps)
    # Pending (None) components are excluded, never summed as zero.
    assert total == 182 + 90 + 28 + 28
    assert status == STATUS_PARTIAL
    assert pending == ["Envío", "Aduana"]


@pytest.mark.unit
def test_recompute_complete_when_all_filled():
    comps = [CostComponent(k, k, 100) for k in ("materials", "labor", "packaging", "shipping", "customs", "indirect")]
    _, total, status, pending = recompute(comps)
    assert total == 600
    assert status == STATUS_COMPLETE
    assert pending == []


@pytest.mark.unit
def test_recompute_override_is_the_scenario_core():
    """The read-only scenario path (D-022, wired to Timonel in M5) reuses this:
    an override changes a component without mutating the input list."""
    comps = [
        CostComponent("materials", "Materiales", 182),
        CostComponent("shipping", "Envío", None),
    ]
    # Fill the pending shipping via an override.
    _, total, status, _ = recompute(comps, {"shipping": 50})
    assert total == 232 and status == STATUS_COMPLETE
    # Force a filled component pending via an override of None.
    _, total2, status2, pending2 = recompute(comps, {"materials": None, "shipping": 50})
    assert total2 == 50 and status2 == STATUS_PARTIAL and pending2 == ["Materiales"]
    # The input list is untouched.
    assert comps[0].cents == 182 and comps[1].cents is None


# ------------------------------------------------------------ AC8 landed_cost

@pytest.mark.unit
@pytest.mark.database
def test_landed_cost_partial_with_pending_components(test_db):
    import database

    country = "Colombia"
    product_id = 1
    with database.get_conn() as conn:
        cafe = _seed_cost_input(conn, "cafe")
        madera = _seed_cost_input(conn, "maderita")
        # cafe: 100 usd-cents for 10 units -> 10 c/u; bom qty 5 -> 50
        _seed_purchase(conn, cafe, 100, 10)
        _seed_bom(conn, product_id, cafe, country, 5)
        # maderita: 132 usd-cents for 2 units -> 66 c/u; bom qty 2 -> 132
        _seed_purchase(conn, madera, 132, 2)
        _seed_bom(conn, product_id, madera, country, 2)
        # labor: 900-cent batch over 10 completed -> 90 c/u
        conn.execute(
            "INSERT INTO labor_costs (product_id, country, batch_payment_cents, units_completed) VALUES (?, ?, 900, 10)",
            (product_id, country),
        )
        # packaging: 28
        conn.execute(
            "INSERT INTO packaging_costs (product_id, country, usd_amount_cents) VALUES (?, ?, 28)",
            (product_id, country),
        )
        # shipping: a lane row with NULL price -> pending, flagged, not summed as zero
        conn.execute(
            "INSERT INTO shipping_lanes (product_id, country, usd_amount_cents, note) VALUES (?, ?, NULL, 'DHL, por averiguar')",
            (product_id, country),
        )
        # customs: no row -> pending
        # indirect: 2800-cent pool for 2026-10; the denominator is units PRODUCED
        # that month, derived from production_records (M4, AC12), not a stored
        # units_produced column. 2026-W40's Thursday is 2026-10-01, so it maps to
        # month 2026-10. 100 units produced -> 28 c/u (filled).
        conn.execute(
            "INSERT INTO indirect_costs (country, period_month, pool_cents) VALUES (?, '2026-10', 2800)",
            (country,),
        )
        conn.execute(
            "INSERT INTO production_records (country, period_week, units_produced) VALUES (?, '2026-W40', 100)",
            (country,),
        )

    landed = CostingService().landed_cost(product_id, country)

    by_key = {c.key: c for c in landed.components}
    assert by_key["materials"].cents == 182
    assert by_key["labor"].cents == 90
    assert by_key["packaging"].cents == 28
    assert by_key["indirect"].cents == 28
    # the null shipping line is flagged pending, never summed as zero
    assert by_key["shipping"].cents is None
    assert by_key["customs"].cents is None

    assert landed.total_cents == 182 + 90 + 28 + 28  # 328, pending excluded
    assert landed.status == STATUS_PARTIAL
    assert set(landed.pending_labels) == {"Envío", "Aduana"}
    assert landed.filled_count == 4


@pytest.mark.unit
@pytest.mark.database
def test_landed_cost_complete_when_every_component_present(test_db):
    import database

    country = "CostaRica"
    product_id = 2
    with database.get_conn() as conn:
        hilo = _seed_cost_input(conn, "hilo")
        _seed_purchase(conn, hilo, 150, 1)  # 150 c/u
        _seed_bom(conn, product_id, hilo, country, 1)  # materials 150
        conn.execute(
            "INSERT INTO labor_costs (product_id, country, batch_payment_cents, units_completed) VALUES (?, ?, 500, 10)",
            (product_id, country),
        )
        conn.execute(
            "INSERT INTO packaging_costs (product_id, country, usd_amount_cents) VALUES (?, ?, 20)",
            (product_id, country),
        )
        conn.execute(
            "INSERT INTO shipping_lanes (product_id, country, usd_amount_cents) VALUES (?, ?, 40)",
            (product_id, country),
        )
        conn.execute(
            "INSERT INTO customs_duties (product_id, country, usd_amount_cents) VALUES (?, ?, 30)",
            (product_id, country),
        )
        # indirect: 1000-cent pool for 2026-10 over 100 units produced (from
        # production_records, M4/AC12) -> 10 c/u.
        conn.execute(
            "INSERT INTO indirect_costs (country, period_month, pool_cents) VALUES (?, '2026-10', 1000)",
            (country,),
        )
        conn.execute(
            "INSERT INTO production_records (country, period_week, units_produced) VALUES (?, '2026-W40', 100)",
            (country,),
        )

    landed = CostingService().landed_cost(product_id, country)
    assert landed.status == STATUS_COMPLETE
    assert landed.pending_labels == []
    assert landed.total_cents == 150 + 50 + 20 + 40 + 30 + 10  # 300
    assert landed.is_complete


# ------------------------------------------------------------ AC12 indirect pending

@pytest.mark.unit
@pytest.mark.database
def test_indirect_pending_when_zero_production_no_divide_by_zero(test_db):
    import database

    country = "Armenia"
    product_id = 3
    with database.get_conn() as conn:
        conn.execute(
            "INSERT INTO indirect_costs (country, period_month, pool_cents, units_produced) VALUES (?, '2026-10', 5000, 0)",
            (country,),
        )

    # Must not raise ZeroDivisionError; indirect is pending.
    landed = CostingService().landed_cost(product_id, country)
    by_key = {c.key: c for c in landed.components}
    assert by_key["indirect"].cents is None
    assert "Indirectos" in landed.pending_labels


# ------------------------------------------------------------ AC7 input purchases

@pytest.mark.unit
@pytest.mark.database
def test_input_purchase_stores_triplet_and_is_append_only(test_db):
    import database

    repo = CostingRepository()
    with database.get_conn() as conn:
        cost_input_id = _seed_cost_input(conn, "cafe")

    # COP 4000.00 (400000 cents) at 4000 COP/USD -> USD 1.00 (100 cents).
    usd1 = repo.record_input_purchase(
        cost_input_id=cost_input_id,
        original_currency="COP",
        original_amount_cents=400000,
        fx_rate=4000.0,
    )
    assert usd1 == 100

    # A correction: same input, a different rate -> a SECOND row, not a mutation.
    usd2 = repo.record_input_purchase(
        cost_input_id=cost_input_id,
        original_currency="COP",
        original_amount_cents=400000,
        fx_rate=4100.0,
    )
    assert usd2 == round(400000 / 4100.0)  # 98

    rows = repo.list_input_purchases(cost_input_id)
    assert len(rows) == 2, "a correction appends a row; it never mutates the first"

    # The original (oldest) row is intact: its stored triplet is unchanged.
    oldest = rows[-1]
    assert oldest["original_currency"] == "COP"
    assert oldest["original_amount_cents"] == 400000
    assert float(oldest["fx_rate"]) == 4000.0
    assert oldest["usd_amount_cents"] == 100
