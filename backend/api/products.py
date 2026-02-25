"""Product Management API Endpoints."""

from typing import List

from fastapi import APIRouter, HTTPException, Query, status

from backend.api.tenant_scope import tenant_scope
from backend.models.schemas import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    SuccessResponse,
)
from backend.services.products_service import (
    ProductConflictError,
    ProductNotFoundError,
    ProductsService,
)

router = APIRouter()
products_service = ProductsService()


@router.get("/{phone}/products", response_model=List[ProductResponse])
async def list_products(
    phone: str,
    include_inactive: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List products for a tenant."""
    with tenant_scope(phone):
        return products_service.list_products(
            phone=phone,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )


@router.get("/{phone}/products/{product_id}", response_model=ProductResponse)
async def get_product(phone: str, product_id: int):
    """Get product details."""
    with tenant_scope(phone):
        try:
            return products_service.get_product(phone=phone, product_id=product_id)
        except ProductNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc


@router.post("/{phone}/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(phone: str, product: ProductCreate):
    """Create product."""
    with tenant_scope(phone):
        try:
            return products_service.create_product(phone=phone, payload=product)
        except ProductConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create product",
            ) from exc


@router.put("/{phone}/products/{product_id}", response_model=ProductResponse)
async def update_product(phone: str, product_id: int, product: ProductUpdate):
    """Update product."""
    with tenant_scope(phone):
        try:
            return products_service.update_product(
                phone=phone,
                product_id=product_id,
                payload=product,
            )
        except ProductNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ProductConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update product",
            ) from exc


@router.delete("/{phone}/products/{product_id}", response_model=SuccessResponse)
async def deactivate_product(phone: str, product_id: int):
    """Deactivate product (soft delete)."""
    with tenant_scope(phone):
        try:
            result = products_service.deactivate_product(phone=phone, product_id=product_id)
            return SuccessResponse(
                status="ok",
                message=f"Product {product_id} deactivated successfully",
                data=result,
            )
        except ProductNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ProductConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to deactivate product",
            ) from exc

