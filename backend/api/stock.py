"""
Stock Management API Endpoints.
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
    StockAddInput,
    StockMovementResponse,
    StockCurrentResponse,
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


def _movement_row_to_response(row: sqlite3.Row) -> StockMovementResponse:
    """Convert database row to StockMovementResponse."""
    # Convert Row to dict to handle NULL values properly
    row_dict = dict(row)

    return StockMovementResponse(
        id=row_dict["id"],
        product_id=row_dict["product_id"],
        movement_type=row_dict["movement_type"],
        quantity=row_dict["quantity"],
        reason=row_dict.get("reason"),
        reference=row_dict.get("reference"),
        occurred_at=row_dict["occurred_at"],
        created_at=row_dict["created_at"],
        product_name=row_dict.get("product_name"),
        product_sku=row_dict.get("product_sku")
    )


def _stock_current_row_to_response(row: sqlite3.Row) -> StockCurrentResponse:
    """Convert database row to StockCurrentResponse."""
    # Convert Row to dict to handle NULL values properly
    row_dict = dict(row)
    unit_price_cents = row_dict.get("unit_price_cents")
    unit_price_usd = round(unit_price_cents / 100.0, 2) if unit_price_cents is not None else None

    return StockCurrentResponse(
        product_id=row_dict["product_id"],
        sku=row_dict["sku"],
        name=row_dict["name"],
        stock_qty=row_dict["stock_qty"],
        unit_price_cents=unit_price_cents,
        unit_price_usd=unit_price_usd
    )


@router.get("/{phone}/stock", response_model=List[StockCurrentResponse])
async def get_current_stock(phone: str):
    """
    Get current stock for all products.

    Args:
        phone: Phone number in international format

    Returns:
        List of products with current stock quantity

    Raises:
        404: Tenant not found
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        query = """
            SELECT sc.*, p.unit_price_cents
            FROM stock_current sc
            LEFT JOIN products p ON sc.product_id = p.id
            ORDER BY sc.name
        """
        rows = database.fetch_all(query)
        stock = [_stock_current_row_to_response(row) for row in rows]

        return stock

    finally:
        database.DB_PATH = original_db


@router.post("/{phone}/stock/add", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
async def add_stock(phone: str, stock_input: StockAddInput):
    """
    Add stock to a product.

    Args:
        phone: Phone number in international format
        stock_input: Stock addition data

    Returns:
        Success message with updated stock quantity

    Raises:
        404: Tenant or product not found
        400: Invalid data
        500: Failed to add stock
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        # Convert StockAddInput to database format
        stock_data = {
            "product_id": stock_input.product_id,
            "quantity": stock_input.quantity,
            "reason": stock_input.reason,
            "movement_type": stock_input.movement_type
        }

        # Add stock using database.py function
        result = database.add_stock(stock_data)

        if result["status"] != "ok":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to add stock")
            )

        return SuccessResponse(
            status="ok",
            message="Stock added successfully",
            data=result
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {stock_input.product_id} not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add stock: {str(e)}"
        )

    finally:
        database.DB_PATH = original_db


@router.post("/{phone}/stock/adjust", response_model=SuccessResponse)
async def adjust_stock(phone: str, adjustment: dict):
    """
    Adjust stock quantity for a product (can increase or decrease).

    Args:
        phone: Phone number in international format
        adjustment: Dict with product_id, quantity (can be negative), and reason

    Returns:
        Success message with updated stock quantity

    Raises:
        404: Tenant or product not found
        400: Invalid data
        500: Failed to adjust stock
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        product_id = adjustment.get("product_id")
        quantity = adjustment.get("quantity", 0)
        reason = adjustment.get("reason", "Manual adjustment")

        if quantity == 0:
            return SuccessResponse(
                status="ok",
                message="No adjustment needed",
                data={"quantity": 0}
            )

        # Determine movement type based on quantity
        if quantity > 0:
            movement_type = "IN"
            stock_data = {
                "product_id": product_id,
                "quantity": abs(quantity),
                "reason": reason,
                "movement_type": movement_type
            }
            result = database.add_stock(stock_data)
        else:
            movement_type = "OUT"
            stock_data = {
                "product_id": product_id,
                "quantity": abs(quantity),
                "reason": reason,
                "movement_type": movement_type
            }
            result = database.remove_stock(stock_data)

        if result["status"] != "ok":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to adjust stock")
            )

        return SuccessResponse(
            status="ok",
            message=f"Stock adjusted successfully ({'+' if quantity > 0 else ''}{quantity})",
            data=result
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to adjust stock: {str(e)}"
        )

    finally:
        database.DB_PATH = original_db


@router.get("/{phone}/stock/movements", response_model=List[StockMovementResponse])
async def get_stock_movements(phone: str, limit: int = 100, offset: int = 0):
    """
    Get stock movement history.

    Args:
        phone: Phone number in international format
        limit: Maximum number of movements to return (default: 100)
        offset: Number of movements to skip (default: 0)

    Returns:
        List of stock movements

    Raises:
        404: Tenant not found
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        query = """
            SELECT sm.*,
                   p.name AS product_name,
                   p.sku AS product_sku
            FROM stock_movements sm
            LEFT JOIN products p ON sm.product_id = p.id
            ORDER BY sm.occurred_at DESC, sm.created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = database.fetch_all(query, (limit, offset))
        movements = [_movement_row_to_response(row) for row in rows]

        return movements

    finally:
        database.DB_PATH = original_db
