"""Resultado (accumulated net) module.

The platform has no bank/till ledger, so there is no true "cash on hand" figure
in M1. What it does have is paid revenue and expenses, whose difference the
schema derives as ``profit_summary.profit_usd`` = lifetime paid sales minus
lifetime expenses. This module reports THAT, labelled honestly as the
accumulated result, not as cash. A real period cash / runway figure (and any
cash-low attention signal) waits on a cash ledger, so M1 raises no attention
item here (a lifetime-negative result is normal for a young business and would
be permanent strip noise).

One fetch per render: ``snapshot`` opens a single tenant scope and reads the
profit and revenue views once.
"""
from __future__ import annotations

from backend.api.tenant_scope import tenant_scope
from backend.modules.formatting import usd_from_dollars
from backend.modules.protocol import STATUS_EMPTY, STATUS_OK, Headline, ModuleSnapshot
from backend.services.analytics_service import AnalyticsService

# Repointed to the dedicated Resultado page (spec 004 S5 / T-010); the legacy
# ?tab=expenses route was the mislabel (Resultado opened the gastos form).
_ROUTE = "/resultado/{phone}"
_service = AnalyticsService()


def compute_snapshot(profit_usd: float, revenue_usd: float) -> ModuleSnapshot:
    # No paid sales and net zero => a fresh tenant with no financial data yet.
    if not revenue_usd and not profit_usd:
        return ModuleSnapshot(
            headline=Headline(value="USD 0", trend="sin movimientos", trend_tone="flat", status=STATUS_EMPTY),
            attention=[],
        )
    tone = "good" if profit_usd >= 0 else "warn"
    return ModuleSnapshot(
        headline=Headline(
            value=usd_from_dollars(profit_usd),
            trend="acumulado · ventas pagadas menos gastos",
            trend_tone=tone,
            status=STATUS_OK,
        ),
        attention=[],
    )


def snapshot(phone: str) -> ModuleSnapshot:
    with tenant_scope(phone):
        profit = _service.get_profit(phone).profit_usd
        revenue = _service.get_revenue(phone).revenue_usd
    return compute_snapshot(profit, revenue)
