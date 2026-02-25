"""Sales Management API Endpoints."""

import logging
from pathlib import Path as FilePath
import sys
from typing import List

from fastapi import APIRouter, HTTPException, Path, Query, status

# Add parent directory to path
sys.path.append(str(FilePath(__file__).parent.parent.parent))

from backend.api.tenant_scope import tenant_scope
from backend.models.schemas import SaleCreate, SaleResponse, SuccessResponse
from backend.services.sales_service import (
    SaleConflictError,
    SaleNotFoundError,
    SaleValidationError,
    SalesService,
)

router = APIRouter()
logger = logging.getLogger(__name__)
sales_service = SalesService()


@router.get("/{phone}/sales", response_model=List[SaleResponse])
async def list_sales(
    phone: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List sales for a tenant."""
    try:
        with tenant_scope(phone):
            return sales_service.list_sales(phone=phone, limit=limit, offset=offset)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to list sales for tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list sales",
        )


@router.get("/{phone}/sales/{sale_id}", response_model=SaleResponse)
async def get_sale(
    phone: str,
    sale_id: int = Path(..., gt=0),
):
    """Get sale details."""
    try:
        with tenant_scope(phone):
            return sales_service.get_sale(phone=phone, sale_id=sale_id)
    except SaleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch sale %s for tenant %s", sale_id, phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch sale",
        )


@router.post("/{phone}/sales", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
async def create_sale(phone: str, sale: SaleCreate):
    """Register a new sale."""
    try:
        with tenant_scope(phone):
            return sales_service.create_sale(phone=phone, payload=sale)
    except SaleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SaleValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create sale for tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create sale",
        )


@router.delete("/{phone}/sales/{sale_id}", response_model=SuccessResponse)
async def cancel_sale(
    phone: str,
    sale_id: int = Path(..., gt=0),
):
    """Cancel a sale (restores stock if it was PAID)."""
    try:
        with tenant_scope(phone):
            result = sales_service.cancel_sale(phone=phone, sale_id=sale_id)
            return SuccessResponse(
                status="ok",
                message=f"Sale {sale_id} cancelled successfully",
                data=result,
            )
    except SaleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SaleConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except SaleValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to cancel sale %s for tenant %s", sale_id, phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel sale",
        )
