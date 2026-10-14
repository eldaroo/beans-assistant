"""Logistics module tests (spec 003 M4, T-016 / AC8 shipping + customs).

AC8: shipping and customs are landed-cost components; a null line is flagged and
excluded, never summed as zero. T-016 ships the Logistica module: the per-country
shipping + customs lens and the pending-customs attention signal, computed from
stored data with no message sent.
"""
import pytest

from backend.repositories.costing_repository import CostingRepository
from backend.services.logistics_service import LogisticsLane, LogisticsService
from backend.modules.providers import logistica_module
from backend.modules.protocol import Severity


# ---------------------------------------------------------- pure LogisticsLane

@pytest.mark.unit
def test_lane_complete_sums_shipping_and_customs():
    lane = LogisticsLane(country="Colombia", shipping_cents=4000, customs_cents=3000)
    assert lane.is_complete
    assert lane.total_cents == 7000
    assert lane.pending_labels == []
    assert lane.customs_pending is False


@pytest.mark.unit
def test_lane_pending_customs_excluded_not_zero():
    lane = LogisticsLane(country="Colombia", shipping_cents=4000, customs_cents=None)
    assert lane.is_complete is False
    assert lane.total_cents is None  # never 4000, never summed as zero customs
    assert lane.pending_labels == ["Aduana"]
    assert lane.customs_pending is True


@pytest.mark.unit
def test_lane_pending_both():
    lane = LogisticsLane(country="Costa Rica", shipping_cents=None, customs_cents=None)
    assert lane.pending_labels == ["Envío", "Aduana"]
    assert lane.total_cents is None


# ----------------------------------------------------- service over stored data

@pytest.mark.unit
@pytest.mark.database
def test_lanes_for_reads_shipping_and_customs(test_db):
    import database

    product_id = 1
    with database.get_conn() as conn:
        # Make the product costable so list_bracelet_types/lead picks it up.
        cur = conn.execute("INSERT INTO cost_inputs (name, category, unit) VALUES ('cafe', 'cafe', 'u')")
        ci = cur.lastrowid
        conn.execute("INSERT INTO bom_lines (product_id, cost_input_id, country, quantity) VALUES (?, ?, 'Colombia', 1)", (product_id, ci))
        conn.execute("INSERT INTO shipping_lanes (product_id, country, usd_amount_cents, note) VALUES (?, 'Colombia', 4000, 'DHL')", (product_id,))
        conn.execute("INSERT INTO customs_duties (product_id, country, usd_amount_cents) VALUES (?, 'Colombia', 3000)", (product_id,))
        # Costa Rica: a shipping lane but customs pending (null) -> the signal.
        conn.execute("INSERT INTO shipping_lanes (product_id, country, usd_amount_cents) VALUES (?, 'Costa Rica', 5000)", (product_id,))
        conn.execute("INSERT INTO customs_duties (product_id, country, usd_amount_cents, note) VALUES (?, 'Costa Rica', NULL, 'HS por confirmar')", (product_id,))

    lanes = {ln.country: ln for ln in LogisticsService().lanes_for(product_id)}
    assert lanes["Colombia"].total_cents == 7000
    assert lanes["Costa Rica"].customs_pending is True
    assert lanes["Costa Rica"].total_cents is None


@pytest.mark.unit
@pytest.mark.database
def test_pending_customs_signal_from_stored_data(test_db):
    import database

    product_id = 1
    with database.get_conn() as conn:
        cur = conn.execute("INSERT INTO cost_inputs (name, category, unit) VALUES ('cafe', 'cafe', 'u')")
        ci = cur.lastrowid
        conn.execute("INSERT INTO bom_lines (product_id, cost_input_id, country, quantity) VALUES (?, ?, 'Colombia', 1)", (product_id, ci))
        # Colombia customs filled, Costa Rica customs pending.
        conn.execute("INSERT INTO customs_duties (product_id, country, usd_amount_cents) VALUES (?, 'Colombia', 3000)", (product_id,))
        conn.execute("INSERT INTO customs_duties (product_id, country, usd_amount_cents) VALUES (?, 'Costa Rica', NULL)", (product_id,))

    pending = LogisticsService().pending_customs()
    countries = {ln.country for ln in pending}
    # Colombia not pending; Costa Rica + Armenia-Colombia (no row at all) pending.
    assert "Colombia" not in countries
    assert "Costa Rica" in countries
    assert "Armenia-Colombia" in countries


@pytest.mark.unit
@pytest.mark.database
def test_logistics_write_paths(test_db):
    import database

    repo = CostingRepository()
    with database.get_conn():
        repo.record_shipping_lane(product_id=1, country="Colombia", usd_amount_cents=4200, note="FedEx")
        repo.record_customs_duty(product_id=1, country="Colombia", usd_amount_cents=None, note="pendiente")
    ship = repo.shipping_lane(1, "Colombia")
    cust = repo.customs_duty(1, "Colombia")
    assert ship["usd_amount_cents"] == 4200
    assert cust["usd_amount_cents"] is None  # recorded as pending, not zero


# ----------------------------------------------------------- module snapshot

@pytest.mark.unit
def test_tile_shows_cheapest_complete_logistics():
    lanes = [
        LogisticsLane("Colombia", shipping_cents=4000, customs_cents=3000),   # 7000
        LogisticsLane("Costa Rica", shipping_cents=5000, customs_cents=4000),  # 9000
        LogisticsLane("Armenia-Colombia", shipping_cents=None, customs_cents=None),
    ]
    snap = logistica_module.compute_snapshot(lanes, "123")
    assert snap.headline.value == "USD 70.00"
    assert "Colombia" in snap.headline.trend
    assert snap.headline.trend_tone == "good"
    # The pending Armenia lane raises customs + shipping signals.
    texts = [a.text for a in snap.attention]
    assert any("Aduana pendiente en Armenia-Colombia" == t for t in texts)
    assert any(a.severity == Severity.MID and "Aduana" in a.text for a in snap.attention)


@pytest.mark.unit
def test_tile_pending_when_none_complete():
    lanes = [
        LogisticsLane("Colombia", shipping_cents=4000, customs_cents=None),
        LogisticsLane("Costa Rica", shipping_cents=None, customs_cents=None),
    ]
    snap = logistica_module.compute_snapshot(lanes, "123")
    assert snap.headline.value == "—"
    assert snap.headline.trend_tone == "warn"
    assert "sin costo completo" in snap.headline.trend


@pytest.mark.unit
def test_tile_empty_when_no_lanes():
    snap = logistica_module.compute_snapshot(None, "123")
    assert snap.headline.status == "empty"
    assert snap.attention == []
