"""Indirect-cost allocation tests (spec 003 M4, T-014 / AC12).

AC12: indirect cost allocates per unit as the indirect pool for a country in a
calendar month divided by units PRODUCED there that month; a month with zero
recorded production renders indirect PENDING, not a divide-by-zero. The units
come from production_records, attributed by the production period (the week's
Thursday), never by the data-entry date (D-M3-9), and a same-week append-only
correction is not double-counted.
"""
import pytest

from backend.repositories.costing_repository import CostingRepository
from backend.services.costing_service import (
    CostingService,
    month_of_iso_week,
    units_in_month,
)


# ------------------------------------------------- pure: week -> calendar month

@pytest.mark.unit
def test_month_of_iso_week_uses_the_thursday():
    # 2026-W40's Thursday is 2026-10-01 -> October. 2026-W01's Thursday is
    # 2026-01-01 -> January. 2026-W53's Thursday is 2026-12-31 -> December
    # (2026 starts on a Thursday, so it has 53 ISO weeks).
    assert month_of_iso_week("2026-W40") == "2026-10"
    assert month_of_iso_week("2026-W01") == "2026-01"
    assert month_of_iso_week("2026-W53") == "2026-12"


@pytest.mark.unit
def test_month_of_iso_week_rejects_malformed():
    with pytest.raises(ValueError):
        month_of_iso_week("2026-10")  # a month, not an ISO week
    with pytest.raises(ValueError):
        month_of_iso_week("garbage")


@pytest.mark.unit
def test_units_in_month_sums_weeks_in_that_month():
    # W40 (Oct 1) + W41 (Oct 8) fall in October; W45 (Nov 5) in November.
    rows = [
        {"period_week": "2026-W40", "units": 60},
        {"period_week": "2026-W41", "units": 40},
        {"period_week": "2026-W45", "units": 30},
    ]
    assert units_in_month(rows, "2026-10") == 100
    assert units_in_month(rows, "2026-11") == 30
    assert units_in_month(rows, "2026-09") == 0  # no week falls here


# ------------------------------------------------- service: indirect_per_unit

@pytest.mark.unit
@pytest.mark.database
def test_indirect_per_unit_divides_pool_by_produced_units(test_db):
    import database

    country = "Colombia"
    with database.get_conn() as conn:
        conn.execute(
            "INSERT INTO indirect_costs (country, period_month, pool_cents) VALUES (?, '2026-10', 3000)",
            (country,),
        )
        # 100 units produced across two October weeks (W40 + W41).
        conn.execute(
            "INSERT INTO production_records (country, period_week, units_produced) VALUES (?, '2026-W40', 70)",
            (country,),
        )
        conn.execute(
            "INSERT INTO production_records (country, period_week, units_produced) VALUES (?, '2026-W41', 30)",
            (country,),
        )

    cents, detail = CostingService().indirect_per_unit(country)
    assert cents == 30  # 3000 / 100
    assert "2026-10" in detail and "100 u" in detail


@pytest.mark.unit
@pytest.mark.database
def test_indirect_pending_when_no_production_that_month(test_db):
    import database

    country = "Armenia-Colombia"
    with database.get_conn() as conn:
        # A pool is recorded but no production in that month -> pending, no /0.
        conn.execute(
            "INSERT INTO indirect_costs (country, period_month, pool_cents) VALUES (?, '2026-10', 5000)",
            (country,),
        )

    cents, detail = CostingService().indirect_per_unit(country)
    assert cents is None
    assert "sin producción" in detail


@pytest.mark.unit
@pytest.mark.database
def test_indirect_pending_when_no_pool_loaded(test_db):
    import database

    country = "Costa Rica"
    with database.get_conn() as conn:
        # Production exists but no indirect pool -> pending with the pool reason.
        conn.execute(
            "INSERT INTO production_records (country, period_week, units_produced) VALUES (?, '2026-W40', 50)",
            (country,),
        )

    cents, detail = CostingService().indirect_per_unit(country)
    assert cents is None
    assert "sin pool" in detail


@pytest.mark.unit
@pytest.mark.database
def test_same_week_correction_not_double_counted(test_db):
    import database

    country = "Colombia"
    with database.get_conn() as conn:
        conn.execute(
            "INSERT INTO indirect_costs (country, period_month, pool_cents) VALUES (?, '2026-10', 2000)",
            (country,),
        )
        # Original W40 record then a correction for the SAME week (newest wins).
        conn.execute(
            "INSERT INTO production_records (country, period_week, units_produced) VALUES (?, '2026-W40', 50)",
            (country,),
        )
        conn.execute(
            "INSERT INTO production_records (country, period_week, units_produced) VALUES (?, '2026-W40', 100)",
            (country,),
        )

    cents, _ = CostingService().indirect_per_unit(country)
    # 2000 / 100 (the corrected value), NOT 2000 / 150 (double-count).
    assert cents == 20


@pytest.mark.unit
@pytest.mark.database
def test_record_indirect_pool_write_path(test_db):
    import database

    repo = CostingRepository()
    with database.get_conn():
        repo.record_indirect_pool(country="Colombia", period_month="2026-10", pool_cents=4000)
    row = repo.indirect_pool_latest("Colombia")
    assert row["pool_cents"] == 4000
    assert row["period_month"] == "2026-10"


@pytest.mark.unit
@pytest.mark.database
def test_build_components_indirect_comes_from_production(test_db):
    """The landed cost's indirect component is now sourced from production_records,
    not a stored units_produced column (the M4 wiring, AC12)."""
    import database

    country = "Colombia"
    product_id = 1
    with database.get_conn() as conn:
        conn.execute(
            "INSERT INTO indirect_costs (country, period_month, pool_cents) VALUES (?, '2026-10', 1000)",
            (country,),
        )
        conn.execute(
            "INSERT INTO production_records (country, period_week, units_produced) VALUES (?, '2026-W40', 100)",
            (country,),
        )

    components = CostingService().build_components(product_id, country)
    indirect = {c.key: c for c in components}["indirect"]
    assert indirect.cents == 10  # 1000 / 100
