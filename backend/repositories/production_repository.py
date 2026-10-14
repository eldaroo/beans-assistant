"""Data-access repository for the production module (spec 003 M3).

SQL only; the units-vs-target and arrival-cadence arithmetic lives in
``production_service`` (ARCHITECTURE convention: repository does SQL, service
computes). Queries use ``%s`` placeholders; the SQLite backend translates them.

A production record is one country's units produced in one ISO week against a
target, with the date the next batch is expected (``expected_next_at``). Records
are append-only: a correction is a new row, newest wins, and the history stays
re-checkable (the same discipline as input_purchases, AC7).
"""

from database_config import db as database


class ProductionRepository:
    """Encapsulates SQL/data access for production."""

    def __init__(self, db_module=database):
        self.db = db_module

    @staticmethod
    def normalize_week(period_week: str) -> str:
        """Enforce zero-padded ISO ``YYYY-Www`` so lexical ordering is correct.

        ``period_week`` is compared and MAX'd as a string, so an un-padded
        ``2026-W9`` would sort AFTER ``2026-W12`` and silently pick the wrong week
        (council MED). Normalizing on write guarantees the ordering; a malformed
        week fails loud at the write rather than mis-ordering silently."""
        import re

        m = re.fullmatch(r"(\d{4})-W(\d{1,2})", str(period_week).strip())
        if not m:
            raise ValueError(f"period_week must be ISO 'YYYY-Www': {period_week!r}")
        year, wk = m.group(1), int(m.group(2))
        if not 1 <= wk <= 53:
            raise ValueError(f"ISO week out of range (1-53): {period_week!r}")
        return f"{year}-W{wk:02d}"

    def record_production(
        self,
        *,
        country: str,
        period_week: str,
        units_produced: int,
        units_target=None,
        expected_next_at=None,
        product_id=None,
        recorded_at=None,
    ) -> None:
        """Append one weekly production record. Append-only: a correction is a new
        row (newest wins); no existing row is ever mutated. The week is normalized
        to zero-padded ISO on write so every ordering/MAX over period_week is sound."""
        from datetime import date

        query = """
            INSERT INTO production_records
              (product_id, country, period_week, units_produced, units_target,
               expected_next_at, recorded_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        self.db.execute(
            query,
            (
                product_id,
                country,
                self.normalize_week(period_week),
                units_produced,
                units_target,
                expected_next_at,
                recorded_at or date.today().isoformat(),
            ),
        )

    def latest(self, country=None):
        """The most recent production record overall (the home tile) or for one
        country. None when nothing is recorded yet."""
        if country is None:
            query = """
                SELECT product_id, country, period_week, units_produced,
                       units_target, expected_next_at, recorded_at
                FROM production_records
                ORDER BY period_week DESC, id DESC
                LIMIT 1
            """
            return self.db.fetch_one(query)
        query = """
            SELECT product_id, country, period_week, units_produced,
                   units_target, expected_next_at, recorded_at
            FROM production_records
            WHERE country = %s
            ORDER BY period_week DESC, id DESC
            LIMIT 1
        """
        return self.db.fetch_one(query, (country,))

    def latest_per_country(self):
        """The most recent production record for each country (newest row of its
        latest week), newest week first. Feeds the drill-down's per-country rows
        and the overdue-arrival scan.

        The per-country row is picked by a correlated subquery mirroring
        ``latest()``'s ``ORDER BY period_week DESC, id DESC LIMIT 1``, so a
        same-week append-only correction (a new row, newest wins) yields ONE row
        per country, never the duplicate a plain ``MAX(period_week)`` join returns
        (council HIGH)."""
        query = """
            SELECT p.product_id, p.country, p.period_week, p.units_produced,
                   p.units_target, p.expected_next_at, p.recorded_at
            FROM production_records p
            WHERE p.id = (
                SELECT x.id FROM production_records x
                WHERE x.country = p.country
                ORDER BY x.period_week DESC, x.id DESC
                LIMIT 1
            )
            ORDER BY p.period_week DESC, p.id DESC
        """
        return self.db.fetch_all(query)

    def latest_week(self):
        """The most recent ISO week with any production recorded. None when empty."""
        row = self.db.fetch_one("SELECT MAX(period_week) AS w FROM production_records")
        return row["w"] if row and row["w"] else None

    def week_rollup(self, period_week: str):
        """Company-wide units and target for one week, summing the NEWEST record
        per country (a same-week correction, newest wins, is not double-counted).
        ``target`` is the SUM of the targets that were SET (NULL only when no
        country set a meta); a week where one country set a target and another did
        not compares full units against that partial target, so the tile percent
        is "progress against the goals that exist", not a business-wide denominator.
        This is the home scorecard number (OQ3 units-this-week-vs-target across the
        business), deterministic rather than whichever country's row was inserted last."""
        query = """
            SELECT COALESCE(SUM(p.units_produced), 0) AS units,
                   SUM(p.units_target) AS target,
                   COUNT(*) AS countries
            FROM production_records p
            WHERE p.period_week = %s
              AND p.id = (
                SELECT x.id FROM production_records x
                WHERE x.country = p.country AND x.period_week = p.period_week
                ORDER BY x.id DESC
                LIMIT 1
              )
        """
        return self.db.fetch_one(query, (period_week,))

    # The indirect-allocation denominator (units produced per country per month),
    # wired in M4 (OQ1 default: calendar month). The month cannot be derived in
    # SQL portably (SQLite and Postgres disagree on ISO-week date math), so the
    # repository returns the deduped weekly units for a country and the service
    # maps each week to its calendar month and sums (see costing_service.units_in_month).
    def weekly_units(self, country: str):
        """Units produced per ISO week for a country, summing the NEWEST record
        per (country, period_week) so a same-week append-only correction (newest
        wins) is not double-counted (the same dedup discipline as week_rollup and
        latest_per_country). Returns ``[{period_week, units}]`` newest week first.
        The service derives the calendar month from period_week and sums per month
        to build the indirect-allocation denominator (AC12)."""
        query = """
            SELECT p.period_week AS period_week,
                   p.units_produced AS units
            FROM production_records p
            WHERE p.country = %s
              AND p.id = (
                SELECT x.id FROM production_records x
                WHERE x.country = p.country AND x.period_week = p.period_week
                ORDER BY x.id DESC
                LIMIT 1
              )
            ORDER BY p.period_week DESC
        """
        return self.db.fetch_all(query, (country,))
