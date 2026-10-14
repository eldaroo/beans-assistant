"""Multi-country comparison and margin tests (spec 003 M4, T-015 / AC9).

AC9: the costing module exposes a margin-per-country headline and a per-country
comparison for one bracelet type across the three countries, each with its
completeness state, and marks the lowest COMPLETE total. A margin is a real
number only when the landed cost is complete and a sale price is set; a parcial
total never wins the "cheapest to land" mark.
"""
import pytest

from backend.repositories.costing_repository import CostingRepository
from backend.services.costing_service import CostingService
from backend.modules.providers import costos_module


def _seed_product(conn, sku, name, price_cents):
    cur = conn.execute(
        "INSERT INTO products (sku, name, unit_cost_cents, unit_price_cents) VALUES (?, ?, 0, ?)",
        (sku, name, price_cents),
    )
    return cur.lastrowid


def _seed_complete_country(conn, product_id, country, *, materials, labor_batch,
                           labor_units, packaging, shipping, customs, pool, produced):
    """Seed every component so (product, country) lands a COMPLETE cost."""
    cur = conn.execute(
        "INSERT INTO cost_inputs (name, category, unit) VALUES (?, 'cafe', 'u')",
        (f"input-{country}",),
    )
    ci = cur.lastrowid
    # One input priced at `materials` c/u, bom qty 1 -> materials == materials.
    conn.execute(
        "INSERT INTO input_purchases (cost_input_id, original_currency, original_amount_cents, "
        "fx_rate, usd_amount_cents, quantity) VALUES (?, 'USD', ?, 1.0, ?, 1)",
        (ci, materials, materials),
    )
    conn.execute(
        "INSERT INTO bom_lines (product_id, cost_input_id, country, quantity) VALUES (?, ?, ?, 1)",
        (product_id, ci, country),
    )
    conn.execute(
        "INSERT INTO labor_costs (product_id, country, batch_payment_cents, units_completed) VALUES (?, ?, ?, ?)",
        (product_id, country, labor_batch, labor_units),
    )
    conn.execute(
        "INSERT INTO packaging_costs (product_id, country, usd_amount_cents) VALUES (?, ?, ?)",
        (product_id, country, packaging),
    )
    conn.execute(
        "INSERT INTO shipping_lanes (product_id, country, usd_amount_cents) VALUES (?, ?, ?)",
        (product_id, country, shipping),
    )
    conn.execute(
        "INSERT INTO customs_duties (product_id, country, usd_amount_cents) VALUES (?, ?, ?)",
        (product_id, country, customs),
    )
    conn.execute(
        "INSERT INTO indirect_costs (country, period_month, pool_cents) VALUES (?, '2026-10', ?)",
        (country, pool),
    )
    conn.execute(
        "INSERT INTO production_records (country, period_week, units_produced) VALUES (?, '2026-W40', ?)",
        (country, produced),
    )


@pytest.fixture
def seeded(test_db):
    import database

    with database.get_conn() as conn:
        pid = _seed_product(conn, "BRAC-LEAD", "Pulsera café clásica", 40000)
        # Colombia: total 100 + 50 + 20 + 40 + 30 + 10 = 250 (complete, cheapest)
        _seed_complete_country(conn, pid, "Colombia", materials=10000, labor_batch=5000,
                               labor_units=100, packaging=2000, shipping=4000, customs=3000,
                               pool=1000, produced=100)
        # Costa Rica: materials 200 -> total 350 (complete, pricier)
        _seed_complete_country(conn, pid, "Costa Rica", materials=20000, labor_batch=5000,
                               labor_units=100, packaging=2000, shipping=4000, customs=3000,
                               pool=1000, produced=100)
        # Armenia-Colombia: only a materials input, everything else pending (parcial)
        cur = conn.execute("INSERT INTO cost_inputs (name, category, unit) VALUES ('hilo-arm', 'hilo', 'u')")
        ci = cur.lastrowid
        conn.execute(
            "INSERT INTO input_purchases (cost_input_id, original_currency, original_amount_cents, "
            "fx_rate, usd_amount_cents, quantity) VALUES (?, 'USD', 5000, 1.0, 5000, 1)",
            (ci,),
        )
        conn.execute(
            "INSERT INTO bom_lines (product_id, cost_input_id, country, quantity) VALUES (?, ?, 'Armenia-Colombia', 1)",
            (pid, ci),
        )
    return pid


@pytest.mark.unit
@pytest.mark.database
def test_comparison_marks_lowest_complete(seeded):
    comp = CostingService().country_comparison(seeded)
    by_country = {m.country: m for m in comp.margins}
    # All three countries present, in THREE_COUNTRIES order.
    assert [m.country for m in comp.margins] == ["Colombia", "Armenia-Colombia", "Costa Rica"]
    # Colombia: materials 10000 + labor 50 + packaging 2000 + shipping 4000 +
    # customs 3000 + indirect 10 = 19060. Costa Rica differs only by materials
    # (20000) -> 29060.
    assert by_country["Colombia"].landed.total_cents == 19060
    assert by_country["Costa Rica"].landed.total_cents == 29060
    # Colombia is the lowest COMPLETE total.
    assert comp.lowest_complete_country == "Colombia"


@pytest.mark.unit
@pytest.mark.database
def test_margin_is_price_minus_complete_cost(seeded):
    comp = CostingService().country_comparison(seeded)
    by_country = {m.country: m for m in comp.margins}
    # price 40000 - landed 19060 = 20940
    assert by_country["Colombia"].margin_cents == 20940
    assert by_country["Colombia"].is_pending is False
    # Costa Rica: 40000 - 29060 = 10940
    assert by_country["Costa Rica"].margin_cents == 10940


@pytest.mark.unit
@pytest.mark.database
def test_margin_pending_on_partial_cost(seeded):
    comp = CostingService().country_comparison(seeded)
    arm = {m.country: m for m in comp.margins}["Armenia-Colombia"]
    # A parcial landed cost yields no margin (never computed off a partial cost).
    assert arm.margin_cents is None
    assert arm.is_pending is True
    assert "parcial" in arm.pending_reason
    # And a parcial country never wins the cheapest-complete mark.
    assert comp.lowest_complete_country != "Armenia-Colombia"


@pytest.mark.unit
@pytest.mark.database
def test_margin_pending_when_no_price(test_db):
    import database

    with database.get_conn() as conn:
        # A product with NO sale price set; complete cost.
        pid = _seed_product(conn, "BRAC-NOPRICE", "Sin precio", None)
        _seed_complete_country(conn, pid, "Colombia", materials=10000, labor_batch=5000,
                               labor_units=100, packaging=2000, shipping=4000, customs=3000,
                               pool=1000, produced=100)

    m = CostingService().margin(pid, "Colombia")
    assert m.margin_cents is None
    assert "sin precio" in m.pending_reason


@pytest.mark.unit
@pytest.mark.database
def test_costos_tile_shows_margin_of_cheapest_complete(seeded):
    """The Costos home tile headlines the margin of the lowest-complete country (AC9)."""
    comp = CostingService().country_comparison(seeded)
    snap = costos_module.compute_snapshot(comp, "123")
    # Colombia is cheapest-complete: margin 20940 cents -> "USD 209.40".
    assert snap.headline.value == "USD 209.40"
    assert "Colombia" in snap.headline.trend
    assert snap.headline.trend_tone == "good"


@pytest.mark.unit
@pytest.mark.database
def test_costos_tile_complete_cost_no_price_shows_cost_not_zero_margin(test_db):
    """A complete landed cost with NO sale price must never headline a fabricated
    'USD 0' margin (council Edut BLOCKER); it shows the cost and says 'sin precio'."""
    import database
    from backend.modules.providers import costos_module

    with database.get_conn() as conn:
        pid = _seed_product(conn, "BRAC-NOPRICE2", "Sin precio", None)
        _seed_complete_country(conn, pid, "Colombia", materials=10000, labor_batch=5000,
                               labor_units=100, packaging=2000, shipping=4000, customs=3000,
                               pool=1000, produced=100)

    comp = CostingService().country_comparison(pid)
    snap = costos_module.compute_snapshot(comp, "123")
    # Complete Colombia cost = 10000+50+2000+4000+3000+10 = 19060 -> "USD 190.60".
    assert snap.headline.value == "USD 190.60"
    assert snap.headline.value != "USD 0"
    assert "sin precio" in snap.headline.trend
    assert snap.headline.trend_tone == "flat"  # never a confident "good" margin


@pytest.mark.unit
def test_costos_tile_falls_back_to_parcial_when_none_complete():
    """With no complete country, the tile shows the lead country's parcial landed
    cost with the honesty '+', never a fabricated margin."""
    from backend.services.costing_service import CountryComparison, Margin, LandedCost, CostComponent

    partial = LandedCost(
        product_id=1, product_name="X", country="Colombia",
        components=[CostComponent("materials", "Materiales", 5000),
                    CostComponent("shipping", "Envío", None)],
        total_cents=5000, status="parcial", pending_labels=["Envío"],
    )
    comp = CountryComparison(
        product_id=1, product_name="X",
        margins=[Margin(country="Colombia", landed=partial, price_cents=None,
                        margin_cents=None, pending_reason="costo parcial")],
        lowest_complete_country=None,
    )
    snap = costos_module.compute_snapshot(comp, "123")
    assert snap.headline.value.endswith("+")
    assert snap.headline.trend_tone == "warn"
