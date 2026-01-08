"""
Expenses Management API Endpoints.
"""
from fastapi import APIRouter, HTTPException, status
from typing import List
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.models.schemas import (
    ExpenseCreate,
    ExpenseResponse,
    SuccessResponse
)
from database_config import db as database

router = APIRouter()


def _expense_row_to_response(row: dict) -> ExpenseResponse:
    """Convert database row to ExpenseResponse."""
    from datetime import date

    row_dict = dict(row)

    # Convert datetime/date to string if needed (PostgreSQL returns datetime/date objects)
    expense_date = row_dict["expense_date"]
    if isinstance(expense_date, datetime):
        expense_date = expense_date.date().isoformat()  # Date only
    elif isinstance(expense_date, date):
        expense_date = expense_date.isoformat()

    created_at = row_dict["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    return ExpenseResponse(
        id=row_dict["id"],
        expense_date=expense_date,
        category=row_dict["category"],
        description=row_dict["description"],
        amount_cents=row_dict["amount_cents"],
        currency=row_dict["currency"],
        created_at=created_at,
        amount_usd=round(row_dict["amount_cents"] / 100.0, 2)
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
    query = """
        SELECT * FROM expenses
        ORDER BY expense_date DESC, created_at DESC
        LIMIT %s OFFSET %s
    """
    rows = database.fetch_all(query, (limit, offset))
    expenses = [_expense_row_to_response(row) for row in rows]

    return expenses


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
        query = "SELECT * FROM expenses WHERE id = %s"
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
