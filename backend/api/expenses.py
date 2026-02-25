"""Expenses Management API Endpoints."""

import logging
from pathlib import Path as FilePath
import sys
from typing import List

from fastapi import APIRouter, HTTPException, Path, Query, status

# Add parent directory to path
sys.path.append(str(FilePath(__file__).parent.parent.parent))

from backend.api.tenant_scope import tenant_scope
from backend.models.schemas import ExpenseCreate, ExpenseResponse, SuccessResponse
from backend.services.expenses_service import (
    ExpenseConflictError,
    ExpenseNotFoundError,
    ExpenseValidationError,
    ExpensesService,
)

router = APIRouter()
logger = logging.getLogger(__name__)
expenses_service = ExpensesService()


@router.get("/{phone}/expenses", response_model=List[ExpenseResponse])
async def list_expenses(
    phone: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List expenses for a tenant."""
    try:
        with tenant_scope(phone):
            return expenses_service.list_expenses(phone=phone, limit=limit, offset=offset)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to list expenses for tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list expenses",
        )


@router.post("/{phone}/expenses", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(phone: str, expense: ExpenseCreate):
    """Register a new expense."""
    try:
        with tenant_scope(phone):
            return expenses_service.create_expense(phone=phone, payload=expense)
    except ExpenseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ExpenseValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to create expense for tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create expense",
        )


@router.delete("/{phone}/expenses/{expense_id}", response_model=SuccessResponse)
async def cancel_expense(
    phone: str,
    expense_id: int = Path(..., gt=0),
):
    """Cancel an expense (delete it)."""
    try:
        with tenant_scope(phone):
            result = expenses_service.cancel_expense(phone=phone, expense_id=expense_id)
            return SuccessResponse(
                status="ok",
                message=f"Expense {expense_id} cancelled successfully",
                data=result,
            )
    except ExpenseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ExpenseConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ExpenseValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to cancel expense %s for tenant %s", expense_id, phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel expense",
        )
