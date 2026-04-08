"""Service layer for tenant management use-cases."""

from backend.api.tenant_scope import tenant_scope
from backend.models.schemas import TenantCreate, TenantResponse, TenantStats
from backend.repositories.tenants_repository import TenantsRepository


class TenantNotFoundError(ValueError):
    """Raised when a tenant does not exist."""


class TenantConflictError(ValueError):
    """Raised when a tenant operation conflicts with current state."""


class TenantsService:
    """Orchestrates tenant repository and response mapping."""

    def __init__(self, repository: TenantsRepository | None = None):
        self.repository = repository or TenantsRepository()

    def list_tenants(self, limit: int, offset: int) -> list[TenantResponse]:
        tenants = self.repository.list_tenants()
        tenants = sorted(tenants, key=lambda t: t.get("created_at", ""), reverse=True)
        tenants = tenants[offset:offset + limit]

        return [
            TenantResponse(
                phone_number=t["phone_number"],
                business_name=t["business_name"],
                currency=t.get("currency", "USD"),
                language=t.get("language", "es"),
                created_at=t["created_at"],
                status=t["status"],
            )
            for t in tenants
        ]

    def get_tenant(self, phone: str) -> TenantResponse:
        if not self.repository.tenant_exists(phone):
            raise TenantNotFoundError(f"Tenant {phone} not found")

        config = self.repository.get_tenant_config(phone)
        if not config:
            raise TenantNotFoundError(f"Tenant {phone} config not found")

        tenants = self.repository.list_tenants()
        tenant_data = next((t for t in tenants if t["phone_number"] == phone), None)

        return TenantResponse(
            phone_number=phone,
            business_name=config.get("business_name", "Unknown"),
            currency=config.get("currency", "USD"),
            language=config.get("language", "es"),
            created_at=tenant_data["created_at"] if tenant_data else "Unknown",
            status=tenant_data["status"] if tenant_data else "active",
        )

    def create_tenant(self, payload: TenantCreate):
        if self.repository.tenant_exists(payload.phone_number):
            raise TenantConflictError(f"Tenant {payload.phone_number} already exists")

        self.repository.create_tenant(
            phone=payload.phone_number,
            business_name=payload.business_name,
            currency=payload.currency,
            language=payload.language,
        )
        self.repository.create_schema_if_needed(payload.phone_number)

    def get_tenant_stats(self, phone: str) -> TenantStats:
        with tenant_scope(phone):
            products_count = self.repository.get_products_count()
            sales_count = self.repository.get_sales_count()
            revenue = self.repository.get_revenue_row()
            profit = self.repository.get_profit_row()
            stock_total = self.repository.get_stock_total_row()

        return TenantStats(
            products_count=products_count.get("count", 0) if products_count else 0,
            sales_count=sales_count.get("count", 0) if sales_count else 0,
            revenue_usd=((revenue.get("total_revenue_cents", 0) or 0) / 100.0) if revenue else 0.0,
            profit_usd=profit.get("profit_usd", 0.0) if profit else 0.0,
            stock_total=stock_total.get("total", 0) if stock_total else 0,
        )

    def get_tenant_by_lid(self, lid: str) -> TenantResponse:
        cfg = self.repository.tenant_manager.get_tenant_by_lid(lid)
        if not cfg:
            raise TenantNotFoundError(f"No tenant found for LID {lid}")
        phone = cfg["phone_number"]
        return TenantResponse(
            phone_number=phone,
            business_name=cfg.get("business_name", "Unknown"),
            currency=cfg.get("currency", "USD"),
            language=cfg.get("language", "es"),
            created_at=cfg.get("created_at", "Unknown"),
            status=cfg.get("status", "active"),
        )

    def set_tenant_lid(self, phone: str, lid: str):
        if not self.repository.tenant_exists(phone):
            raise TenantNotFoundError(f"Tenant {phone} not found")
        self.repository.tenant_manager.set_tenant_lid(phone, lid)

    def delete_tenant(self, phone: str):
        if not self.repository.tenant_exists(phone):
            raise TenantNotFoundError(f"Tenant {phone} not found")

        tenant_path = self.repository.get_tenant_path(phone)
        self.repository.drop_schema_if_needed(phone)
        self.repository.remove_tenant_from_registry(phone)
        self.repository.delete_tenant_directory(tenant_path)
