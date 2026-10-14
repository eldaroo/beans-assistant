"""Production service tests (spec 003 M3, T-011 / AC11 production side).

Covers:
  - the Produccion tile reads the latest recorded week's units against its target
    (percent, meets-target tone);
  - an overdue expected arrival surfaces as an arrival-cadence signal computed
    from stored data, with no message sent (AC13's production-side analog);
  - no production recorded yet reads as empty, never a false zero;
  - a same-week append-only correction is deduped (newest wins) in both the
    per-country drill-down and the company-wide home rollup;
  - the week is stored zero-padded so lexical ordering is sound.
"""
from datetime import date

import pytest

from backend.repositories.production_repository import ProductionRepository
from backend.services.production_service import ProductionService, _is_overdue


def _seed(conn, **row):
    conn.execute(
        "INSERT INTO production_records (product_id, country, period_week, units_produced, "
        "units_target, expected_next_at, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            row.get("product_id"),
            row["country"],
            row["period_week"],
            row["units_produced"],
            row.get("units_target"),
            row.get("expected_next_at"),
            row.get("recorded_at", "2026-10-13"),
        ),
    )


# ------------------------------------------------------------- pure overdue

@pytest.mark.unit
def test_is_overdue_pure():
    today = date(2026, 10, 13)
    assert _is_overdue("2026-10-10", today) is True       # past -> overdue
    assert _is_overdue("2026-10-13", today) is True       # due today -> overdue
    assert _is_overdue("2026-10-20", today) is False      # future -> not overdue
    assert _is_overdue(None, today) is False              # unknown -> never a false alarm
    assert _is_overdue("", today) is False
    assert _is_overdue("not-a-date", today) is False


# ------------------------------------------------------- units vs target tile

@pytest.mark.unit
@pytest.mark.database
def test_current_week_units_against_target_single_country(test_db):
    import database

    with database.get_conn() as conn:
        _seed(conn, country="Colombia", period_week="2026-W41", units_produced=200, units_target=300, recorded_at="2026-10-06")
        _seed(conn, country="Colombia", period_week="2026-W42", units_produced=240, units_target=300, recorded_at="2026-10-13")

    status = ProductionService().current_week(country="Colombia", today=date(2026, 10, 13))
    assert status.period_week == "2026-W42", "the tile reads the latest week, not an older one"
    assert status.units_produced == 240
    assert status.units_target == 300
    assert status.pct_of_target == 80
    assert status.meets_target is False


@pytest.mark.unit
@pytest.mark.database
def test_home_tile_aggregates_across_countries(test_db):
    """The home scorecard (country=None) sums the latest week across countries,
    deterministically, not whichever country's row was inserted last (council MED)."""
    import database

    with database.get_conn() as conn:
        _seed(conn, country="Colombia", period_week="2026-W42", units_produced=240, units_target=300)
        _seed(conn, country="CostaRica", period_week="2026-W42", units_produced=310, units_target=300)
        # an older week must not fold into the latest-week rollup
        _seed(conn, country="Armenia", period_week="2026-W41", units_produced=999, units_target=999, recorded_at="2026-10-06")

    status = ProductionService().current_week(today=date(2026, 10, 13))
    assert status.period_week == "2026-W42"
    assert status.units_produced == 550, "240 + 310 across the two countries in the latest week"
    assert status.units_target == 600, "300 + 300 targets summed"
    assert status.pct_of_target == 92  # round(550/600*100)


@pytest.mark.unit
@pytest.mark.database
def test_pct_floors_to_one_for_tiny_nonzero_progress(test_db):
    import database

    with database.get_conn() as conn:
        _seed(conn, country="Colombia", period_week="2026-W42", units_produced=1, units_target=1000)

    status = ProductionService().current_week(country="Colombia", today=date(2026, 10, 13))
    assert status.pct_of_target == 1, "1 unit against a 1000 target shows 1%, never a false 0%"


@pytest.mark.unit
@pytest.mark.database
def test_current_week_meets_target(test_db):
    import database

    with database.get_conn() as conn:
        _seed(conn, country="CostaRica", period_week="2026-W42", units_produced=310, units_target=300)

    status = ProductionService().current_week(country="CostaRica", today=date(2026, 10, 13))
    assert status.meets_target is True
    assert status.pct_of_target == 103


@pytest.mark.unit
@pytest.mark.database
def test_no_production_reads_empty(test_db):
    assert ProductionService().current_week(today=date(2026, 10, 13)) is None


# --------------------------------------------------------- overdue arrivals

@pytest.mark.unit
@pytest.mark.database
def test_overdue_arrival_surfaces_from_stored_data(test_db):
    import database

    with database.get_conn() as conn:
        # Colombia's next batch was expected before today -> overdue.
        _seed(conn, country="Colombia", period_week="2026-W42", units_produced=240,
              units_target=300, expected_next_at="2026-10-10")
        # Armenia's next batch is in the future -> not overdue.
        _seed(conn, country="Armenia", period_week="2026-W42", units_produced=150,
              units_target=150, expected_next_at="2026-10-20")

    overdue = ProductionService().overdue_arrivals(today=date(2026, 10, 13))
    countries = {s.country for s in overdue}
    assert countries == {"Colombia"}, "only the past-due country surfaces, computed from stored data"


# ----------------------------------- same-week correction (append-only, newest wins)

@pytest.mark.unit
@pytest.mark.database
def test_latest_per_country_dedups_same_week_correction(test_db):
    """A same-week correction (a new row, newest wins) must yield ONE row per
    country, not a duplicate (council HIGH). The drill-down and the overdue scan
    both read latest_per_country."""
    import database

    with database.get_conn() as conn:
        _seed(conn, country="Colombia", period_week="2026-W42", units_produced=200, units_target=300)
        _seed(conn, country="Colombia", period_week="2026-W42", units_produced=240, units_target=300)  # correction

    rows = [s for s in ProductionService().per_country(today=date(2026, 10, 13)) if s.country == "Colombia"]
    assert len(rows) == 1, "a same-week correction yields one row, newest wins"
    assert rows[0].units_produced == 240, "the newest correction wins"


@pytest.mark.unit
@pytest.mark.database
def test_home_rollup_does_not_double_count_same_week_correction(test_db):
    import database

    with database.get_conn() as conn:
        _seed(conn, country="Colombia", period_week="2026-W42", units_produced=200, units_target=300)
        _seed(conn, country="Colombia", period_week="2026-W42", units_produced=260, units_target=300)  # correction

    status = ProductionService().current_week(today=date(2026, 10, 13))
    assert status.units_produced == 260, "the corrected value, not 200+260=460"


# --------------------------------------------- zero-padded week on write

@pytest.mark.unit
@pytest.mark.database
def test_period_week_zero_padded_on_write_keeps_ordering_sound(test_db):
    import database

    repo = ProductionRepository()
    # W9 un-padded would sort AFTER W12 lexically; normalization fixes it.
    repo.record_production(country="Colombia", period_week="2026-W9", units_produced=50, units_target=100)
    repo.record_production(country="Colombia", period_week="2026-W12", units_produced=90, units_target=100)

    with database.get_conn() as conn:
        weeks = [r["period_week"] for r in conn.execute(
            "SELECT period_week FROM production_records ORDER BY id").fetchall()]
    assert weeks == ["2026-W09", "2026-W12"], "the week is stored zero-padded"

    status = ProductionService().current_week(country="Colombia", today=date(2026, 10, 13))
    assert status.period_week == "2026-W12", "W12 is the latest week, not W09 by bad lexical order"


@pytest.mark.unit
def test_normalize_week_rejects_malformed():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        ProductionRepository.normalize_week("octubre")
    with _pytest.raises(ValueError):
        ProductionRepository.normalize_week("2026-W99")
    assert ProductionRepository.normalize_week("2026-W3") == "2026-W03"
