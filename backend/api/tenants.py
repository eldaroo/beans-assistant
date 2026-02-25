"""Tenant Management API Endpoints."""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query, status

from backend.models.schemas import SuccessResponse, TenantCreate, TenantResponse, TenantStats
from backend.services.tenants_service import (
    TenantConflictError,
    TenantNotFoundError,
    TenantsService,
)

router = APIRouter()
logger = logging.getLogger(__name__)
tenants_service = TenantsService()


@router.get("", response_model=List[TenantResponse])
async def list_tenants(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List all tenants."""
    try:
        return tenants_service.list_tenants(limit=limit, offset=offset)
    except Exception:
        logger.exception("Failed to list tenants")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list tenants",
        )


@router.get("/{phone}", response_model=TenantResponse)
async def get_tenant(phone: str):
    """Get tenant details by phone number."""
    try:
        return tenants_service.get_tenant(phone)
    except TenantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception:
        logger.exception("Failed to fetch tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch tenant",
        )


@router.post("", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(tenant: TenantCreate):
    """Create a new tenant."""
    try:
        tenants_service.create_tenant(tenant)
        return SuccessResponse(
            status="ok",
            message=f"Tenant {tenant.phone_number} created successfully",
            data={"phone_number": tenant.phone_number},
        )
    except TenantConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Exception:
        logger.exception("Failed to create tenant %s", tenant.phone_number)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create tenant",
        )


@router.get("/{phone}/stats", response_model=TenantStats)
async def get_tenant_stats(phone: str):
    """Get tenant statistics."""
    try:
        return tenants_service.get_tenant_stats(phone)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch tenant stats for %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch tenant stats",
        )


@router.delete("/{phone}", response_model=SuccessResponse)
async def delete_tenant(phone: str):
    """Delete a tenant and all tenant data."""
    try:
        tenants_service.delete_tenant(phone)
        return SuccessResponse(
            status="ok",
            message=f"Tenant {phone} deleted successfully",
        )
    except TenantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception:
        logger.exception("Failed to delete tenant %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete tenant",
        )
