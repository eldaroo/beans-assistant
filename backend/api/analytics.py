"""
Analytics API Endpoints.
"""
from fastapi import APIRouter, HTTPException, status
from typing import List
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.models.schemas import (
    RevenueResponse,
    ProfitResponse,
    SalesSummaryItem
)
from database_config import db as database

router = APIRouter()


@router.get("/{phone}/analytics/revenue", response_model=RevenueResponse)
async def get_revenue(phone: str):
    """
    Get total revenue from paid sales.

    Args:
        phone: Phone number in international format

    Returns:
        Total revenue in cents and USD

    Raises:
        404: Tenant not found
    """
    query = "SELECT * FROM revenue_paid"
    row = database.fetch_one(query)

    if not row:
        return RevenueResponse(
            total_revenue_cents=0,
            revenue_usd=0.0
        )

    return RevenueResponse(
        total_revenue_cents=row["total_revenue_cents"] or 0,
        revenue_usd=round((row["total_revenue_cents"] or 0) / 100.0, 2)
    )


@router.get("/{phone}/analytics/profit", response_model=ProfitResponse)
async def get_profit(phone: str):
    """
    Get current profit (revenue - expenses).

    Args:
        phone: Phone number in international format

    Returns:
        Profit in USD

    Raises:
        404: Tenant not found
    """
    query = "SELECT * FROM profit_summary"
    row = database.fetch_one(query)

    if not row:
        return ProfitResponse(profit_usd=0.0)

    return ProfitResponse(
        profit_usd=row["profit_usd"] or 0.0
    )


@router.get("/{phone}/analytics/sales-summary", response_model=List[SalesSummaryItem])
async def get_sales_summary(phone: str, limit: int = 30):
    """
    Get daily sales summary.

    Args:
        phone: Phone number in international format
        limit: Number of days to return (default: 30)

    Returns:
        List of daily sales summaries

    Raises:
        404: Tenant not found
    """
    query = """
        SELECT * FROM sales_summary
        ORDER BY day DESC
        LIMIT %s
    """
    rows = database.fetch_all(query, (limit,))

    summaries = [
        SalesSummaryItem(
            day=row["day"],
            paid_sales_count=row["paid_sales_count"],
            paid_revenue_cents=row["paid_revenue_cents"],
            paid_revenue_usd=round(row["paid_revenue_cents"] / 100.0, 2)
        )
        for row in rows
    ]

    return summaries
