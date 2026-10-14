"""Service layer for the logistics module (spec 003 M4, T-016).

Reads the shipping lane and customs duty for a bracelet type into each country
and derives the Logistica tile and the pending-customs attention signal. The two
logistics components (shipping, customs) are the same rows the landed cost reads;
this module is the dedicated lens on them. A line that is null or missing is
PENDING, never summed as zero (AC8); the pending-customs signal is computed from
stored data, no message is sent. Pure arithmetic lives here; SQL in the repository.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.repositories.costing_repository import CostingRepository
from backend.services.costing_service import THREE_COUNTRIES


@dataclass(frozen=True)
class LogisticsLane:
    """Shipping plus customs for a bracelet type into one country. A None cents is
    PENDING (unknown yet), excluded from the total, never a real zero (AC8)."""

    country: str
    shipping_cents: Optional[int]
    customs_cents: Optional[int]
    shipping_note: Optional[str] = None
    customs_note: Optional[str] = None

    @property
    def is_complete(self) -> bool:
        return self.shipping_cents is not None and self.customs_cents is not None

    @property
    def total_cents(self) -> Optional[int]:
        """Shipping plus customs when BOTH are filled; None when either is pending
        (a partial logistics cost is never rendered as a finished number)."""
        if not self.is_complete:
            return None
        return int(self.shipping_cents) + int(self.customs_cents)

    @property
    def pending_labels(self) -> "list[str]":
        out = []
        if self.shipping_cents is None:
            out.append("Envío")
        if self.customs_cents is None:
            out.append("Aduana")
        return out

    @property
    def customs_pending(self) -> bool:
        return self.customs_cents is None


class LogisticsService:
    """Orchestrates the costing repository for the logistics lens."""

    def __init__(self, repository: CostingRepository | None = None):
        self.repository = repository or CostingRepository()

    def _lane(self, product_id, country) -> LogisticsLane:
        ship = self.repository.shipping_lane(product_id, country)
        cust = self.repository.customs_duty(product_id, country)
        ship_cents = ship["usd_amount_cents"] if ship and ship["usd_amount_cents"] is not None else None
        cust_cents = cust["usd_amount_cents"] if cust and cust["usd_amount_cents"] is not None else None
        return LogisticsLane(
            country=country,
            shipping_cents=(int(ship_cents) if ship_cents is not None else None),
            customs_cents=(int(cust_cents) if cust_cents is not None else None),
            shipping_note=(ship["note"] if ship else None),
            customs_note=(cust["note"] if cust else None),
        )

    def lanes_for(self, product_id, countries=None) -> "list[LogisticsLane]":
        """The logistics lane for a bracelet type into each country (AC8)."""
        countries = countries or THREE_COUNTRIES
        return [self._lane(product_id, c) for c in countries]

    def lead_lanes(self) -> "Optional[list[LogisticsLane]]":
        """Logistics lanes for the lead bracelet type across the three countries,
        for the Logistica tile and drill-down. None when no costable type exists."""
        types = self.repository.list_bracelet_types()
        if not types:
            return None
        return self.lanes_for(types[0]["id"])

    def pending_customs(self) -> "list[LogisticsLane]":
        """Lanes of the lead type whose customs is pending (the pending-customs
        attention signal, computed from stored data, no message sent). Empty when
        there is no costable type yet."""
        lanes = self.lead_lanes()
        if lanes is None:
            return []
        return [ln for ln in lanes if ln.customs_pending]
