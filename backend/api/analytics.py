"""
Analytics API Endpoints.
"""
from fastapi import APIRouter, HTTPException, status
from typing import List
import sys
from pathlib import Path
import sqlite3

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from tenant_manager import TenantManager
from backend.models.schemas import (
    RevenueResponse,
    ProfitResponse,
    SalesSummaryItem
)
from database_config import db as database

router = APIRouter()


def _get_tenant_db_uri(phone: str) -> str:
    """Get database URI for a tenant."""
    tenant_manager = TenantManager()
    if not tenant_manager.tenant_exists(phone):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {phone} not found"
        )
    return tenant_manager.get_tenant_db_path(phone)


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
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        query = "SELECT * FROM revenue_paid"
        row = database.fetch_one(query)

        if not row:
            return RevenueResponse(
                total_revenue_cents=0,
                revenue_usd=0.0
            )

        return RevenueResponse(
            total_revenue_cents=row["total_revenue_cents"] or 0,
            revenue_usd=row["revenue_usd"] or 0.0
        )

    finally:
        database.DB_PATH = original_db


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
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        query = "SELECT * FROM profit_summary"
        row = database.fetch_one(query)

        if not row:
            return ProfitResponse(profit_usd=0.0)

        return ProfitResponse(
            profit_usd=row["profit_usd"] or 0.0
        )

    finally:
        database.DB_PATH = original_db


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
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        query = """
            SELECT * FROM sales_summary
            ORDER BY day DESC
            LIMIT ?
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

    finally:
        database.DB_PATH = original_db
