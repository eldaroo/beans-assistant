"""Service layer for analytics use-cases."""

from backend.models.schemas import ProfitResponse, RevenueResponse, SalesSummaryItem
from backend.repositories.analytics_repository import AnalyticsRepository


class AnalyticsService:
    """Orchestrates analytics repository and response mapping."""

    def __init__(self, repository: AnalyticsRepository | None = None):
        self.repository = repository or AnalyticsRepository()

    def get_revenue(self, phone: str) -> RevenueResponse:
        row = self.repository.get_revenue_row()
        if not row:
            return RevenueResponse(total_revenue_cents=0, revenue_usd=0.0)

        total_revenue_cents = row["total_revenue_cents"] or 0
        return RevenueResponse(
            total_revenue_cents=total_revenue_cents,
            revenue_usd=round(total_revenue_cents / 100.0, 2),
        )

    def get_profit(self, phone: str) -> ProfitResponse:
        row = self.repository.get_profit_row()
        if not row:
            return ProfitResponse(profit_usd=0.0)
        return ProfitResponse(profit_usd=row["profit_usd"] or 0.0)

    def get_sales_summary(self, phone: str, limit: int) -> list[SalesSummaryItem]:
        rows = self.repository.get_sales_summary_rows(limit=limit)
        return [
            SalesSummaryItem(
                day=row["day"],
                paid_sales_count=row["paid_sales_count"],
                paid_revenue_cents=row["paid_revenue_cents"],
                paid_revenue_usd=round(row["paid_revenue_cents"] / 100.0, 2),
            )
            for row in rows
        ]
