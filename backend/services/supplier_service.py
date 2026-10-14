"""Service layer for the suppliers module (spec 003 M5, T-017 / T-018).

Reads the supplier directory and derives the overdue-check-in attention signal.
AC13: an overdue supplier check-in (no recorded reply within the configured
window) surfaces as an attention item computed from stored data, with no message
sent. Pure arithmetic lives here; SQL in the repository.

A supplier with NO recorded check-in yet (``last_checkin_at`` null) is NOT
overdue: a freshly added supplier should not raise an alarm before any cadence
exists (the same "blank date is never overdue" discipline as the production
arrival-cadence signal, D-M3-2). Overdue is an active supplier whose last
check-in is older than the window.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from backend.repositories.supplier_repository import SupplierRepository

# OQ4 default: the check-in cadence the overdue signal measures against. Surfaced
# as a setting later; a sensible starting window the CEO can tune.
CHECKIN_WINDOW_DAYS = 14


@dataclass(frozen=True)
class SupplierStatus:
    """One supplier for the directory and the overdue scan."""

    id: int
    name: str
    country: Optional[str]
    contact: Optional[str]
    is_active: bool
    last_checkin_at: Optional[str]
    is_overdue: bool
    days_since_checkin: Optional[int]


def _parse_day(value) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _days_since(last_checkin_at, today: date) -> Optional[int]:
    d = _parse_day(last_checkin_at)
    if d is None:
        return None
    return (today - d).days


def _is_overdue(last_checkin_at, today: date, window_days: int) -> bool:
    """Overdue when there IS a recorded check-in and it is strictly older than the
    window. A null or unparseable date is never overdue (no false alarm)."""
    days = _days_since(last_checkin_at, today)
    if days is None:
        return False
    return days > window_days


class SupplierService:
    """Orchestrates the supplier repository and the overdue-check-in compute."""

    def __init__(self, repository: SupplierRepository | None = None,
                 window_days: int = CHECKIN_WINDOW_DAYS):
        self.repository = repository or SupplierRepository()
        self.window_days = window_days

    def _status_from(self, row, today: date) -> SupplierStatus:
        last = row["last_checkin_at"]
        return SupplierStatus(
            id=int(row["id"]),
            name=row["name"],
            country=row["country"],
            contact=row["contact"],
            is_active=bool(row["is_active"]),
            last_checkin_at=last,
            is_overdue=_is_overdue(last, today, self.window_days),
            days_since_checkin=_days_since(last, today),
        )

    def directory(self, today: Optional[date] = None) -> "list[SupplierStatus]":
        """The active supplier directory with each one's check-in status (T-017)."""
        today = today or date.today()
        return [self._status_from(r, today) for r in self.repository.list_suppliers(active_only=True)]

    def count_active(self) -> int:
        return self.repository.count_active()

    def overdue_checkins(self, today: Optional[date] = None) -> "list[SupplierStatus]":
        """Active suppliers whose last check-in is older than the window (AC13).
        Computed from stored data; no message is sent."""
        return [s for s in self.directory(today) if s.is_overdue]
