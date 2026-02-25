"""Stock Management API Endpoints."""

import logging
from pathlib import Path
import sys
from typing import List

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.api.tenant_scope import tenant_scope
from backend.models.schemas import StockAddInput, StockCurrentResponse, StockMovementResponse, SuccessResponse
from backend.services.stock_service import StockNotFoundError, StockService, StockValidationError

router = APIRouter()
logger = logging.getLogger(__name__)
stock_service = StockService()


class StockAdjustInput(BaseModel):
    """Payload for manual stock adjustments."""

    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., description="Can be positive or negative; 0 means no-op")
    reason: str = Field(default="Manual adjustment")


@router.get("/{phone}/stock", response_model=List[StockCurrentResponse])
async def get_current_stock(
    phone: str,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Get current stock for all products."""
    try:
        with tenant_scope(phone):
            return stock_service.get_current_stock(phone=phone, limit=limit, offset=offset)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch current stock for tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch current stock",
        )


@router.post("/{phone}/stock/add", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
async def add_stock(phone: str, stock_input: StockAddInput):
    """Add stock to a product."""
    try:
        with tenant_scope(phone):
            result = stock_service.add_stock(phone=phone, stock_input=stock_input)
            return SuccessResponse(
                status="ok",
                message="Stock added successfully",
                data=result,
            )
    except StockNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except StockValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to add stock for tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add stock",
        )


@router.post("/{phone}/stock/adjust", response_model=SuccessResponse)
async def adjust_stock(phone: str, adjustment: StockAdjustInput):
    """Adjust stock quantity for a product (can increase or decrease)."""
    try:
        with tenant_scope(phone):
            message, data = stock_service.adjust_stock(
                phone=phone,
                product_id=adjustment.product_id,
                quantity=adjustment.quantity,
                reason=adjustment.reason,
            )
            return SuccessResponse(status="ok", message=message, data=data)
    except StockNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except StockValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to adjust stock for tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to adjust stock",
        )


@router.get("/{phone}/stock/movements", response_model=List[StockMovementResponse])
async def get_stock_movements(
    phone: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Get stock movement history."""
    try:
        with tenant_scope(phone):
            return stock_service.get_stock_movements(phone=phone, limit=limit, offset=offset)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch stock movements for tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch stock movements",
        )
