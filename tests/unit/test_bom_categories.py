"""BOM input-category breadth (spec 003 M3, T-012).

Coffee, roasting, wood, thread, stones, and clasps are each enterable as inputs
through the costing write paths and each appears in the BOM materials total, and
a per-unit packaging cost appears in the landed total. This exercises the real
record_cost_input / record_bom_line / record_input_purchase / record_packaging_cost
write paths, not a hand-seeded INSERT, so the enter-path is what is proven.
"""
import pytest

from backend.services.costing_service import INPUT_CATEGORIES, CostingService
from backend.repositories.costing_repository import CostingRepository


@pytest.mark.unit
def test_input_categories_are_the_six_bracelet_inputs():
    keys = [k for k, _ in INPUT_CATEGORIES]
    assert keys == ["cafe", "tostado", "madera", "hilo", "piedras", "broches"], (
        "the canonical six BOM categories: coffee, roasting, wood, thread, stones, clasps"
    )


@pytest.mark.unit
@pytest.mark.database
def test_all_six_categories_enter_and_sum_into_materials(test_db):
    repo = CostingRepository()
    country = "Colombia"
    product_id = 1

    # Enter one input per category, price each, and add a BOM line of quantity 1.
    # Unit USD cents per category, chosen distinct so the sum is unambiguous.
    unit_cents = {"cafe": 40, "tostado": 10, "madera": 25, "hilo": 15, "piedras": 30, "broches": 20}
    for category, _label in INPUT_CATEGORIES:
        cid = repo.record_cost_input(name=category, category=category, unit="u")
        # price: usd_amount_cents for quantity 1 -> that many cents per unit
        repo.record_input_purchase(
            cost_input_id=cid,
            original_currency="USD",
            original_amount_cents=unit_cents[category],
            fx_rate=1.0,
            quantity=1,
        )
        repo.record_bom_line(product_id=product_id, cost_input_id=cid, country=country, quantity=1)

    # per-unit packaging appears in the landed total.
    repo.record_packaging_cost(product_id=product_id, country=country, usd_amount_cents=12)

    landed = CostingService().landed_cost(product_id, country)
    by_key = {c.key: c for c in landed.components}

    expected_materials = sum(unit_cents.values())  # 40+10+25+15+30+20 = 140
    assert by_key["materials"].cents == expected_materials, "every category sums into materials"
    # the materials detail names each input, so all six are present, none dropped.
    for category, _ in INPUT_CATEGORIES:
        assert category in by_key["materials"].detail, f"{category} missing from the BOM breakdown"

    assert by_key["packaging"].cents == 12, "a per-unit packaging cost appears in the landed total"
    # materials + packaging are both counted toward the (still partial) total.
    assert landed.total_cents >= expected_materials + 12


@pytest.mark.unit
@pytest.mark.database
def test_one_unpriced_category_makes_materials_pending(test_db):
    """Breadth does not weaken the honesty rule: if any BOM input is unpriced the
    whole materials component is pending (named), never summed as zero."""
    repo = CostingRepository()
    country = "Armenia"
    product_id = 2

    cafe = repo.record_cost_input(name="cafe", category="cafe")
    repo.record_input_purchase(cost_input_id=cafe, original_currency="USD",
                               original_amount_cents=40, fx_rate=1.0, quantity=1)
    repo.record_bom_line(product_id=product_id, cost_input_id=cafe, country=country, quantity=1)

    # broches entered as an input + BOM line but never priced.
    broches = repo.record_cost_input(name="broches", category="broches")
    repo.record_bom_line(product_id=product_id, cost_input_id=broches, country=country, quantity=1)

    landed = CostingService().landed_cost(product_id, country)
    by_key = {c.key: c for c in landed.components}
    assert by_key["materials"].cents is None, "an unpriced input makes materials pending, not a partial sum"
    assert "broches" in by_key["materials"].detail, "the unpriced input is named"
    assert "Materiales" in landed.pending_labels
