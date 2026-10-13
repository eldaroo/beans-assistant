"""Display formatting for Control Center headlines.

Money and counts are formatted where the number is owned, never in the shell
or the template. Money renders with the ``USD`` prefix the mockup uses and
collapses thousands to ``k`` so a tile stays one glance wide.
"""
from __future__ import annotations


def usd_from_cents(cents: int | float | None) -> str:
    """Format a USD-cents amount as the mockup's tile money string.

    >=1000 USD collapses to one decimal k ("USD 3.1k"); below that shows full
    cents ("USD 842.50"). A null amount renders "USD 0".
    """
    if not cents:
        return "USD 0"
    dollars = cents / 100.0
    return _usd_from_dollars(dollars)


def usd_from_dollars(dollars: float | int | None) -> str:
    if not dollars:
        return "USD 0"
    return _usd_from_dollars(float(dollars))


def _usd_from_dollars(dollars: float) -> str:
    sign = "-" if dollars < 0 else ""
    mag = abs(dollars)
    if mag >= 1000:
        return f"{sign}USD {mag / 1000:.1f}k"
    return f"{sign}USD {mag:.2f}"


def units(n: int | None) -> str:
    """Format a unit count ("1.2k u" above a thousand, "240 u" below)."""
    n = n or 0
    if abs(n) >= 1000:
        return f"{n / 1000:.1f}k u"
    return f"{n} u"
