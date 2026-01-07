"""
Expenses Management API Endpoints.
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
    ExpenseCreate,
    ExpenseResponse,
    SuccessResponse
)
import database

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


def _expense_row_to_response(row: sqlite3.Row) -> ExpenseResponse:
    """Convert database row to ExpenseResponse."""
    return ExpenseResponse(
        id=row["id"],
        expense_date=row["expense_date"],
        category=row["category"],
        description=row["description"],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        created_at=row["created_at"],
        amount_usd=round(row["amount_cents"] / 100.0, 2)
    )


@router.get("/{phone}/expenses", response_model=List[ExpenseResponse])
async def list_expenses(phone: str, limit: int = 50, offset: int = 0):
    """
    List expenses for a tenant.

    Args:
        phone: Phone number in international format
        limit: Maximum number of expenses to return (default: 50)
        offset: Number of expenses to skip (default: 0)

    Returns:
        List of expenses

    Raises:
        404: Tenant not found
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        query = """
            SELECT * FROM expenses
            ORDER BY expense_date DESC, created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = database.fetch_all(query, (limit, offset))
        expenses = [_expense_row_to_response(row) for row in rows]

        return expenses

    finally:
        database.DB_PATH = original_db


@router.post("/{phone}/expenses", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(phone: str, expense: ExpenseCreate):
    """
    Register a new expense.

    Args:
        phone: Phone number in international format
        expense: Expense data

    Returns:
        Created expense

    Raises:
        404: Tenant not found
        400: Invalid data
        500: Failed to create expense
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        # Convert ExpenseCreate to database format
        expense_data = {
            "amount_cents": expense.amount_cents,
            "description": expense.description,
            "category": expense.category,
            "currency": expense.currency,
            **({"expense_date": expense.expense_date} if expense.expense_date else {})
        }

        # Create expense using database.py function
        result = database.register_expense(expense_data)

        if result["status"] != "ok":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to create expense")
            )

        expense_id = result["expense_id"]

        # Fetch created expense
        query = "SELECT * FROM expenses WHERE id = ?"
        row = database.fetch_one(query, (expense_id,))

        return _expense_row_to_response(row)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create expense: {str(e)}"
        )

    finally:
        database.DB_PATH = original_db


@router.delete("/{phone}/expenses/{expense_id}", response_model=SuccessResponse)
async def cancel_expense(phone: str, expense_id: int):
    """
    Cancel an expense (delete it).

    Args:
        phone: Phone number in international format
        expense_id: Expense ID

    Returns:
        Success message with updated profit

    Raises:
        404: Tenant or expense not found
        500: Failed to cancel expense
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        # Use database.py function
        result = database.cancel_expense(expense_id)

        if result["status"] != "ok":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to cancel expense")
            )

        return SuccessResponse(
            status="ok",
            message=f"Expense {expense_id} cancelled successfully",
            data=result
        )

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Expense {expense_id} not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel expense: {str(e)}"
        )

    finally:
        database.DB_PATH = original_db
