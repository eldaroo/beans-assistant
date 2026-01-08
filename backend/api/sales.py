"""
Sales Management API Endpoints.
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
    SaleCreate,
    SaleResponse,
    SaleItemResponse,
    SuccessResponse
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


def _sale_row_to_response(sale_row: sqlite3.Row, items: List[sqlite3.Row]) -> SaleResponse:
    """Convert database rows to SaleResponse."""
    # Convert Row to dict to handle NULL values properly
    sale_dict = dict(sale_row)

    return SaleResponse(
        id=sale_dict["id"],
        sale_number=sale_dict["sale_number"],
        status=sale_dict["status"],
        total_amount_cents=sale_dict["total_amount_cents"],
        customer_name=sale_dict.get("customer_name"),
        created_at=sale_dict["created_at"],
        paid_at=sale_dict.get("paid_at"),
        total_amount_usd=round(sale_dict["total_amount_cents"] / 100.0, 2),
        items=[
            SaleItemResponse(
                id=item_dict["id"],
                sale_id=item_dict["sale_id"],
                product_id=item_dict["product_id"],
                quantity=item_dict["quantity"],
                unit_price_cents=item_dict["unit_price_cents"],
                line_total_cents=item_dict["line_total_cents"],
                unit_price_usd=round(item_dict["unit_price_cents"] / 100.0, 2),
                line_total_usd=round(item_dict["line_total_cents"] / 100.0, 2),
                product_name=item_dict.get("product_name"),
                product_sku=item_dict.get("product_sku")
            )
            for item in items
            for item_dict in [dict(item)]  # Convert Row to dict
        ]
    )


@router.get("/{phone}/sales", response_model=List[SaleResponse])
async def list_sales(phone: str, limit: int = 50, offset: int = 0):
    """
    List sales for a tenant.

    Args:
        phone: Phone number in international format
        limit: Maximum number of sales to return (default: 50)
        offset: Number of sales to skip (default: 0)

    Returns:
        List of sales with items

    Raises:
        404: Tenant not found
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        # Fetch sales
        sales_query = """
            SELECT * FROM sales
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        sales_rows = database.fetch_all(sales_query, (limit, offset))

        # Fetch items for each sale
        result = []
        for sale_row in sales_rows:
            items_query = """
                SELECT si.*,
                       p.name AS product_name,
                       p.sku AS product_sku
                FROM sale_items si
                LEFT JOIN products p ON si.product_id = p.id
                WHERE si.sale_id = ?
            """
            items_rows = database.fetch_all(items_query, (sale_row["id"],))
            result.append(_sale_row_to_response(sale_row, items_rows))

        return result

    finally:
        database.DB_PATH = original_db


@router.get("/{phone}/sales/{sale_id}", response_model=SaleResponse)
async def get_sale(phone: str, sale_id: int):
    """
    Get sale details.

    Args:
        phone: Phone number in international format
        sale_id: Sale ID

    Returns:
        Sale details with items

    Raises:
        404: Tenant or sale not found
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        sale_query = "SELECT * FROM sales WHERE id = ?"
        sale_row = database.fetch_one(sale_query, (sale_id,))

        if not sale_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sale {sale_id} not found"
            )

        items_query = """
            SELECT si.*,
                   p.name AS product_name,
                   p.sku AS product_sku
            FROM sale_items si
            LEFT JOIN products p ON si.product_id = p.id
            WHERE si.sale_id = ?
        """
        items_rows = database.fetch_all(items_query, (sale_id,))

        return _sale_row_to_response(sale_row, items_rows)

    finally:
        database.DB_PATH = original_db


@router.post("/{phone}/sales", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
async def create_sale(phone: str, sale: SaleCreate):
    """
    Register a new sale.

    Args:
        phone: Phone number in international format
        sale: Sale data with items

    Returns:
        Created sale with updated revenue and profit

    Raises:
        404: Tenant not found
        400: Insufficient stock or invalid data
        500: Failed to create sale
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        # Convert SaleCreate to database format
        items_data = [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                **({"unit_price_cents": item.unit_price_cents} if item.unit_price_cents else {})
            }
            for item in sale.items
        ]

        sale_data = {
            "status": sale.status,
            "items": items_data,
            **({"customer_name": sale.customer_name} if sale.customer_name else {})
        }

        # Create sale using database.py function
        result = database.register_sale(sale_data)

        if result["status"] != "ok":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to create sale")
            )

        sale_id = result["sale_id"]

        # Fetch created sale
        sale_query = "SELECT * FROM sales WHERE id = ?"
        sale_row = database.fetch_one(sale_query, (sale_id,))

        items_query = """
            SELECT si.*,
                   p.name AS product_name,
                   p.sku AS product_sku
            FROM sale_items si
            LEFT JOIN products p ON si.product_id = p.id
            WHERE si.sale_id = ?
        """
        items_rows = database.fetch_all(items_query, (sale_id,))

        return _sale_row_to_response(sale_row, items_rows)

    except ValueError as e:
        # Insufficient stock or validation error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create sale: {str(e)}"
        )

    finally:
        database.DB_PATH = original_db


@router.delete("/{phone}/sales/{sale_id}", response_model=SuccessResponse)
async def cancel_sale(phone: str, sale_id: int):
    """
    Cancel a sale (restores stock if it was PAID).

    Args:
        phone: Phone number in international format
        sale_id: Sale ID

    Returns:
        Success message with updated revenue/profit

    Raises:
        404: Tenant or sale not found
        500: Failed to cancel sale
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        # Use database.py function
        result = database.cancel_sale(sale_id)

        if result["status"] != "ok":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to cancel sale")
            )

        return SuccessResponse(
            status="ok",
            message=f"Sale {sale_id} cancelled successfully",
            data=result
        )

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sale {sale_id} not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel sale: {str(e)}"
        )

    finally:
        database.DB_PATH = original_db
