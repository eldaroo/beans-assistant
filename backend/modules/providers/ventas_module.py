"""Ventas (sales) module: this-week revenue headline.

Headline is paid revenue over the last seven calendar days, summed from the
``sales_summary`` daily view, with the paid-sale count as the caption. The
window is stated in the caption so it is never confused with an all-time figure.
No attention items in M1. One fetch per render.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from backend.api.tenant_scope import tenant_scope
from backend.modules.formatting import usd_from_cents
from backend.modules.protocol import STATUS_EMPTY, STATUS_OK, Headline, ModuleSnapshot
from backend.services.analytics_service import AnalyticsService

_ROUTE = "?tab=sales"
_WINDOW_DAYS = 7
_service = AnalyticsService()


def _parse_day(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def compute_snapshot(rows, today: date | None = None) -> ModuleSnapshot:
    """Sum paid revenue + count over the last ``_WINDOW_DAYS`` calendar days.

    ``rows`` is a list of SalesSummaryItem (one per day). ``today`` is injectable
    so the window is deterministic under test. With no sales rows at all the
    module reports ``empty`` (a fresh or dormant tenant), distinct from a real
    zero-this-week over existing history.
    """
    if not rows:
        return ModuleSnapshot(
            headline=Headline(value="USD 0", trend="sin ventas", trend_tone="flat", status=STATUS_EMPTY),
            attention=[],
        )
    today = today or date.today()
    cutoff = today - timedelta(days=_WINDOW_DAYS - 1)
    cents = 0
    count = 0
    for r in rows:
        day = _parse_day(getattr(r, "day", None))
        if day is None or day < cutoff or day > today:
            continue
        cents += int(getattr(r, "paid_revenue_cents", 0) or 0)
        count += int(getattr(r, "paid_sales_count", 0) or 0)
    noun = "venta" if count == 1 else "ventas"
    return ModuleSnapshot(
        headline=Headline(
            value=usd_from_cents(cents),
            trend=f"{count} {noun} · 7 días",
            trend_tone="good" if count else "flat",
            status=STATUS_OK,
        ),
        attention=[],
    )


def snapshot(phone: str) -> ModuleSnapshot:
    with tenant_scope(phone):
        rows = _service.get_sales_summary(phone=phone, limit=60)
    return compute_snapshot(rows)
