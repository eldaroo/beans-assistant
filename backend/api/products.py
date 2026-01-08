"""
Product Management API Endpoints.
"""
from fastapi import APIRouter, HTTPException, status
from typing import List
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.models.schemas import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    SuccessResponse
)
from database_config import db as database
from backend import cache

router = APIRouter()


def _product_row_to_response(row: dict) -> ProductResponse:
    """Convert database row to ProductResponse."""
    from datetime import datetime

    # Convert Row to dict to handle NULL values properly
    row_dict = dict(row)

    # Convert datetime to string if needed (PostgreSQL returns datetime objects)
    created_at = row_dict["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    return ProductResponse(
        id=row_dict["id"],
        sku=row_dict["sku"],
        name=row_dict["name"],
        description=row_dict.get("description"),
        unit_cost_cents=row_dict["unit_cost_cents"],
        unit_price_cents=row_dict["unit_price_cents"],
        is_active=row_dict["is_active"],
        created_at=created_at,
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
        # Try to get from cache
        cached_products = cache.get_cached_products(phone, active_only=not include_inactive)
        if cached_products is not None:
            return cached_products
        
        # Cache miss - query database
        if include_inactive:
            query = "SELECT * FROM products ORDER BY created_at DESC"
        else:
            query = "SELECT * FROM products WHERE is_active = TRUE ORDER BY created_at DESC"

        rows = database.fetch_all(query)
        products = [_product_row_to_response(row) for row in rows]
        
        # Cache the results
        cache.cache_products(phone, products, active_only=not include_inactive)

        return products

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
    # Try to get from cache
    cached_product = cache.get_cached_product(phone, product_id)
    if cached_product is not None:
        return cached_product
    
    # Cache miss - query database
    query = "SELECT * FROM products WHERE id = %s"
    row = database.fetch_one(query, (product_id,))

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found"
        )

    product = _product_row_to_response(row)
    
    # Cache the result
    cache.cache_product(phone, product_id, product)
    
    return product


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
        query = "SELECT * FROM products WHERE sku = %s"
        row = database.fetch_one(query, (product.sku,))
        
        # Invalidate products cache
        cache.invalidate_products(phone)

        return _product_row_to_response(row)

    except Exception as e:
        error_msg = str(e)
        if "duplicate key" in error_msg.lower() or "unique constraint" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with SKU '{product.sku}' already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create product: {error_msg}"
        )


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
    try:
        # Check if product exists
        query = "SELECT * FROM products WHERE id = %s"
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
            updates.append("sku = %s")
            params.append(product.sku)
        if product.name is not None:
            updates.append("name = %s")
            params.append(product.name)
        if product.description is not None:
            updates.append("description = %s")
            params.append(product.description)
        if product.unit_cost_cents is not None:
            updates.append("unit_cost_cents = %s")
            params.append(product.unit_cost_cents)
        if product.unit_price_cents is not None:
            updates.append("unit_price_cents = %s")
            params.append(product.unit_price_cents)

        if not updates:
            # No updates provided, return current product
            return _product_row_to_response(row)

        # Execute update
        params.append(product_id)
        update_query = f"UPDATE products SET {', '.join(updates)} WHERE id = %s"

        with database.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(update_query, params)

        # Fetch updated product
        row = database.fetch_one(query, (product_id,))
        
        # Invalidate cache
        cache.invalidate_products(phone)
        
        return _product_row_to_response(row)

    except Exception as e:
        error_msg = str(e)
        if "duplicate key" in error_msg.lower() or "unique constraint" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with SKU '{product.sku}' already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update product: {error_msg}"
        )


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
    try:
        # Use database.py function
        result = database.deactivate_product(product_id)

        if result["status"] != "ok":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to deactivate product")
            )
        
        # Invalidate cache
        cache.invalidate_products(phone)

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
