"""Direct labor on a completed-units basis (spec 003 M3, T-013 / AC11).

Marcus: batch labor is a fixed cost masquerading as variable. Labor entered as a
batch payment computes per-unit labor by dividing by units COMPLETED, not units
planned, so a short batch (the same payment over fewer completed units) RAISES
the per-unit labor. Covers the pure core and the write path through the landed
cost.
"""
import pytest

from backend.repositories.costing_repository import CostingRepository
from backend.services.costing_service import CostingService, labor_per_unit


# ---------------------------------------------------------------- pure core

@pytest.mark.unit
def test_short_batch_raises_per_unit_labor():
    # Same batch payment, fewer units completed than planned -> higher per unit.
    full_batch = labor_per_unit(10000, 100)   # 10000c over 100 completed -> 100 c/u
    short_batch = labor_per_unit(10000, 80)   # same pay, only 80 completed -> 125 c/u
    assert full_batch == 100
    assert short_batch == 125
    assert short_batch > full_batch, "a short batch raises the per-unit labor (T-013)"


@pytest.mark.unit
def test_labor_pending_when_no_units_completed_no_divide_by_zero():
    assert labor_per_unit(10000, 0) is None   # never a divide-by-zero
    assert labor_per_unit(10000, None) is None


# --------------------------------------------------- write path through landed

@pytest.mark.unit
@pytest.mark.database
def test_record_labor_batch_feeds_completed_basis_into_landed(test_db):
    repo = CostingRepository()
    country = "CostaRica"
    product_id = 3

    # A short batch: 9000c paid, only 60 units completed -> 150 c/u.
    repo.record_labor_batch(product_id=product_id, country=country,
                            batch_payment_cents=9000, units_completed=60)

    landed = CostingService().landed_cost(product_id, country)
    by_key = {c.key: c for c in landed.components}
    assert by_key["labor"].cents == 150, "landed labor uses the completed-basis per-unit figure"
    assert "lote de 60" in by_key["labor"].detail


@pytest.mark.unit
@pytest.mark.database
def test_latest_labor_batch_wins(test_db):
    """A correction is a new row; the newest batch drives the landed labor."""
    repo = CostingRepository()
    country = "Colombia"
    product_id = 4

    repo.record_labor_batch(product_id=product_id, country=country,
                            batch_payment_cents=10000, units_completed=100)  # 100 c/u
    repo.record_labor_batch(product_id=product_id, country=country,
                            batch_payment_cents=10000, units_completed=80)   # 125 c/u, newest

    landed = CostingService().landed_cost(product_id, country)
    by_key = {c.key: c for c in landed.components}
    assert by_key["labor"].cents == 125, "the newest batch (short) wins in the landed read"
