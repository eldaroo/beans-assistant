"""Service layer for the production module (spec 003 M3).

Reads the production records and derives what the Produccion tile and drill-down
show: units produced this week against a target, and whether the next expected
batch is overdue (the arrival-cadence signal, T-011). Pure arithmetic lives here;
the repository does SQL. The production records this module writes are what M4
reads to build the indirect-allocation denominator, once OQ1 (the allocation
window) is decided; M3 does not ship that month query.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from backend.repositories.production_repository import ProductionRepository


@dataclass(frozen=True)
class ProductionStatus:
    """This week's production for a country against its target, plus the
    arrival-cadence state. ``units_target`` is None when no meta is set for the
    week (never read as a zero target). ``is_overdue`` is True when the next batch
    was expected on or before today and that week has no newer record."""

    country: Optional[str]  # None for the company-wide home rollup across countries
    period_week: str
    units_produced: int
    units_target: Optional[int]
    expected_next_at: Optional[str]
    is_overdue: bool

    @property
    def has_target(self) -> bool:
        return self.units_target is not None and self.units_target > 0

    @property
    def pct_of_target(self) -> Optional[int]:
        """Percent of target produced, rounded. None when there is no target.
        Genuine-but-tiny progress floors to 1%, never a false 0% while real units
        exist (a nonzero quantity must not read as nothing)."""
        if not self.has_target:
            return None
        pct = int(round(100.0 * self.units_produced / self.units_target))
        if pct == 0 and self.units_produced > 0:
            return 1
        return pct

    @property
    def meets_target(self) -> bool:
        return self.has_target and self.units_produced >= (self.units_target or 0)


def _is_overdue(expected_next_at: Optional[str], today: date) -> bool:
    """An expected arrival date on or before today is overdue. A blank or
    unparseable date is never overdue (no false alarm from bad data)."""
    if not expected_next_at:
        return False
    try:
        due = date.fromisoformat(str(expected_next_at)[:10])
    except (ValueError, TypeError):
        return False
    return due <= today


class ProductionService:
    """Orchestrates the production repository and the units-vs-target compute."""

    def __init__(self, repository: ProductionRepository | None = None):
        self.repository = repository or ProductionRepository()

    def _status_from(self, row, today: date) -> Optional[ProductionStatus]:
        if not row:
            return None
        return ProductionStatus(
            country=row["country"],
            period_week=row["period_week"],
            units_produced=int(row["units_produced"] or 0),
            units_target=(int(row["units_target"]) if row["units_target"] is not None else None),
            expected_next_at=row["expected_next_at"],
            is_overdue=_is_overdue(row["expected_next_at"], today),
        )

    def current_week(self, country=None, today: Optional[date] = None) -> Optional[ProductionStatus]:
        """Production for the Produccion tile. None when nothing is recorded yet.

        For one country, the latest week's row for that country. For the home
        scorecard (``country=None``), a company-wide rollup of the latest week:
        units and target SUMMED across countries (the newest record per country,
        so a same-week correction is not double-counted). The rollup is
        deterministic, where picking a single country's last-inserted row would
        be insert-order-dependent and would understate the weekly total (council
        MED)."""
        today = today or date.today()
        if country is not None:
            return self._status_from(self.repository.latest(country), today)

        week = self.repository.latest_week()
        if week is None:
            return None
        roll = self.repository.week_rollup(week)
        target = int(roll["target"]) if roll["target"] is not None else None
        return ProductionStatus(
            country=None,
            period_week=week,
            units_produced=int(roll["units"] or 0),
            units_target=target,
            expected_next_at=None,  # the per-country overdue signals ride the strip, not the tile
            is_overdue=False,
        )

    def per_country(self, today: Optional[date] = None) -> "list[ProductionStatus]":
        """The latest week per country, for the drill-down and the overdue scan."""
        today = today or date.today()
        return [self._status_from(r, today) for r in self.repository.latest_per_country()]

    def overdue_arrivals(self, today: Optional[date] = None) -> "list[ProductionStatus]":
        """Countries whose next expected batch is overdue (the arrival-cadence
        attention signal, computed from stored data; no message is sent)."""
        return [s for s in self.per_country(today) if s and s.is_overdue]
