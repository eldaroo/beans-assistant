"""
Tenant Management API Endpoints.
"""
from fastapi import APIRouter, HTTPException, status
from typing import List
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from tenant_manager import TenantManager
from backend.models.schemas import (
    TenantCreate,
    TenantResponse,
    TenantStats,
    SuccessResponse,
    ErrorResponse
)

router = APIRouter()


@router.get("", response_model=List[TenantResponse])
async def list_tenants():
    """
    List all tenants.

    Returns:
        List of all registered tenants with their configuration
    """
    tenant_manager = TenantManager()
    tenants = tenant_manager.list_tenants()

    return [
        TenantResponse(
            phone_number=t["phone_number"],
            business_name=t["business_name"],
            currency=t.get("currency", "USD"),
            language=t.get("language", "es"),
            created_at=t["created_at"],
            status=t["status"]
        )
        for t in tenants
    ]


@router.get("/{phone}", response_model=TenantResponse)
async def get_tenant(phone: str):
    """
    Get tenant details by phone number.

    Args:
        phone: Phone number in international format (e.g., +5491153695627)

    Returns:
        Tenant configuration and details

    Raises:
        404: Tenant not found
    """
    tenant_manager = TenantManager()

    if not tenant_manager.tenant_exists(phone):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {phone} not found"
        )

    config = tenant_manager.get_tenant_config(phone)

    # Get created_at from registry
    tenants = tenant_manager.list_tenants()
    tenant_data = next((t for t in tenants if t["phone_number"] == phone), None)

    return TenantResponse(
        phone_number=phone,
        business_name=config.get("business_name", "Unknown"),
        currency=config.get("currency", "USD"),
        language=config.get("language", "es"),
        created_at=tenant_data["created_at"] if tenant_data else "Unknown",
        status=tenant_data["status"] if tenant_data else "active"
    )


@router.post("", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(tenant: TenantCreate):
    """
    Create a new tenant.

    Args:
        tenant: Tenant creation data (phone, business name, currency, language)

    Returns:
        Success message with tenant phone number

    Raises:
        400: Tenant already exists or invalid data
    """
    tenant_manager = TenantManager()

    if tenant_manager.tenant_exists(tenant.phone_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant {tenant.phone_number} already exists"
        )

    try:
        # Create tenant with custom config
        custom_config = {
            "currency": tenant.currency,
            "language": tenant.language,
        }

        tenant_manager.create_tenant(
            phone_number=tenant.phone_number,
            business_name=tenant.business_name,
            config=custom_config
        )

        return SuccessResponse(
            status="ok",
            message=f"Tenant {tenant.phone_number} created successfully",
            data={"phone_number": tenant.phone_number}
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create tenant: {str(e)}"
        )


@router.get("/{phone}/stats", response_model=TenantStats)
async def get_tenant_stats(phone: str):
    """
    Get tenant statistics.

    Args:
        phone: Phone number in international format

    Returns:
        Tenant statistics (products count, sales count, revenue, profit, stock total)

    Raises:
        404: Tenant not found
    """
    tenant_manager = TenantManager()

    if not tenant_manager.tenant_exists(phone):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {phone} not found"
        )

    stats = tenant_manager.get_tenant_stats(phone)

    return TenantStats(
        products_count=stats.get("products_count", 0),
        sales_count=stats.get("sales_count", 0),
        revenue_usd=stats.get("revenue_usd", 0.0),
        profit_usd=stats.get("profit_usd", 0.0),
        stock_total=stats.get("stock_total", 0)
    )


@router.delete("/{phone}", response_model=SuccessResponse)
async def delete_tenant(phone: str):
    """
    Delete a tenant.

    WARNING: This will delete all tenant data including database.
    Use with caution.

    Args:
        phone: Phone number in international format

    Returns:
        Success message

    Raises:
        404: Tenant not found
        500: Failed to delete tenant
    """
    tenant_manager = TenantManager()

    if not tenant_manager.tenant_exists(phone):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {phone} not found"
        )

    try:
        # Get tenant path
        tenant_path = tenant_manager.get_tenant_path(phone)

        # Remove from registry
        import json
        registry_path = Path(__file__).parent.parent.parent / "configs" / "tenant_registry.json"

        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)

        if phone in registry:
            del registry[phone]

        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)

        # Delete tenant directory
        import shutil
        if tenant_path.exists():
            shutil.rmtree(tenant_path)

        return SuccessResponse(
            status="ok",
            message=f"Tenant {phone} deleted successfully"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete tenant: {str(e)}"
        )
