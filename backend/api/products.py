"""
Product Management API Endpoints.
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
    ProductCreate,
    ProductUpdate,
    ProductResponse,
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


def _product_row_to_response(row: sqlite3.Row) -> ProductResponse:
    """Convert database row to ProductResponse."""
    # Convert Row to dict to handle NULL values properly
    row_dict = dict(row)

    return ProductResponse(
        id=row_dict["id"],
        sku=row_dict["sku"],
        name=row_dict["name"],
        description=row_dict.get("description"),
        unit_cost_cents=row_dict["unit_cost_cents"],
        unit_price_cents=row_dict["unit_price_cents"],
        is_active=row_dict["is_active"],
        created_at=row_dict["created_at"],
        unit_cost_usd=round(row_dict["unit_cost_cents"] / 100.0, 2),
        unit_price_usd=round(row_dict["unit_price_cents"] / 100.0, 2)
    )


@router.get("/{phone}/products", response_model=List[ProductResponse])
async def list_products(phone: str, include_inactive: bool = False):
    """
    List all products for a tenant.

    Args:
        phone: Phone number in international format
        include_inactive: Include inactive products (default: False)

    Returns:
        List of products

    Raises:
        404: Tenant not found
    """
    import traceback

    try:
        db_uri = _get_tenant_db_uri(phone)

        # Temporarily set database URI
        original_db = database.DB_PATH
        database.DB_PATH = db_uri

        try:
            if include_inactive:
                query = "SELECT * FROM products ORDER BY created_at DESC"
            else:
                query = "SELECT * FROM products WHERE is_active = 1 ORDER BY created_at DESC"

            rows = database.fetch_all(query)
            products = [_product_row_to_response(row) for row in rows]

            return products

        finally:
            database.DB_PATH = original_db
    except Exception as e:
        print(f"ERROR in list_products: {str(e)}")
        print(traceback.format_exc())
        raise


@router.get("/{phone}/products/{product_id}", response_model=ProductResponse)
async def get_product(phone: str, product_id: int):
    """
    Get product details.

    Args:
        phone: Phone number in international format
        product_id: Product ID

    Returns:
        Product details

    Raises:
        404: Tenant or product not found
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        query = "SELECT * FROM products WHERE id = ?"
        row = database.fetch_one(query, (product_id,))

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found"
            )

        return _product_row_to_response(row)

    finally:
        database.DB_PATH = original_db


@router.post("/{phone}/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(phone: str, product: ProductCreate):
    """
    Create a new product.

    Args:
        phone: Phone number in international format
        product: Product data

    Returns:
        Created product

    Raises:
        404: Tenant not found
        400: Product with same SKU already exists
        500: Failed to create product
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        # Create product using database.py function
        result = database.register_product({
            "sku": product.sku,
            "name": product.name,
            "description": product.description,
            "unit_cost_cents": product.unit_cost_cents,
            "unit_price_cents": product.unit_price_cents
        })

        if result["status"] != "ok":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to create product")
            )

        # Fetch created product
        query = "SELECT * FROM products WHERE sku = ?"
        row = database.fetch_one(query, (product.sku,))

        return _product_row_to_response(row)

    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: products.sku" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with SKU '{product.sku}' already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create product: {str(e)}"
        )

    finally:
        database.DB_PATH = original_db


@router.put("/{phone}/products/{product_id}", response_model=ProductResponse)
async def update_product(phone: str, product_id: int, product: ProductUpdate):
    """
    Update a product.

    Args:
        phone: Phone number in international format
        product_id: Product ID
        product: Product update data

    Returns:
        Updated product

    Raises:
        404: Tenant or product not found
        500: Failed to update product
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        # Check if product exists
        query = "SELECT * FROM products WHERE id = ?"
        row = database.fetch_one(query, (product_id,))

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found"
            )

        # Build update query dynamically
        updates = []
        params = []

        if product.sku is not None:
            updates.append("sku = ?")
            params.append(product.sku)
        if product.name is not None:
            updates.append("name = ?")
            params.append(product.name)
        if product.description is not None:
            updates.append("description = ?")
            params.append(product.description)
        if product.unit_cost_cents is not None:
            updates.append("unit_cost_cents = ?")
            params.append(product.unit_cost_cents)
        if product.unit_price_cents is not None:
            updates.append("unit_price_cents = ?")
            params.append(product.unit_price_cents)

        if not updates:
            # No updates provided, return current product
            return _product_row_to_response(row)

        # Execute update
        params.append(product_id)
        update_query = f"UPDATE products SET {', '.join(updates)} WHERE id = ?"

        with database.get_conn() as conn:
            conn.execute(update_query, params)

        # Fetch updated product
        row = database.fetch_one(query, (product_id,))
        return _product_row_to_response(row)

    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: products.sku" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with SKU '{product.sku}' already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update product: {str(e)}"
        )

    finally:
        database.DB_PATH = original_db


@router.delete("/{phone}/products/{product_id}", response_model=SuccessResponse)
async def deactivate_product(phone: str, product_id: int):
    """
    Deactivate a product (soft delete).

    Args:
        phone: Phone number in international format
        product_id: Product ID

    Returns:
        Success message

    Raises:
        404: Tenant or product not found
        500: Failed to deactivate product
    """
    db_uri = _get_tenant_db_uri(phone)

    original_db = database.DB_PATH
    database.DB_PATH = db_uri

    try:
        # Use database.py function
        result = database.deactivate_product(product_id)

        if result["status"] != "ok":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to deactivate product")
            )

        return SuccessResponse(
            status="ok",
            message=f"Product {product_id} deactivated successfully",
            data=result
        )

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate product: {str(e)}"
        )

    finally:
        database.DB_PATH = original_db
