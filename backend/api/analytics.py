"""Analytics API Endpoints."""

import logging
from pathlib import Path
import sys
from typing import List

from fastapi import APIRouter, HTTPException, Query, status

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.api.tenant_scope import tenant_scope
from backend.models.schemas import ProfitResponse, RevenueResponse, SalesSummaryItem
from backend.services.analytics_service import AnalyticsService

router = APIRouter()
logger = logging.getLogger(__name__)
analytics_service = AnalyticsService()


@router.get("/{phone}/analytics/revenue", response_model=RevenueResponse)
async def get_revenue(phone: str):
    """Get total revenue from paid sales."""
    try:
        with tenant_scope(phone):
            return analytics_service.get_revenue(phone=phone)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch revenue for tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch revenue",
        )


@router.get("/{phone}/analytics/profit", response_model=ProfitResponse)
async def get_profit(phone: str):
    """Get current profit (revenue - expenses)."""
    try:
        with tenant_scope(phone):
            return analytics_service.get_profit(phone=phone)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch profit for tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch profit",
        )


@router.get("/{phone}/analytics/sales-summary", response_model=List[SalesSummaryItem])
async def get_sales_summary(
    phone: str,
    limit: int = Query(default=30, ge=1, le=365),
):
    """Get daily sales summary."""
    try:
        with tenant_scope(phone):
            return analytics_service.get_sales_summary(phone=phone, limit=limit)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch sales summary for tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch sales summary",
        )
