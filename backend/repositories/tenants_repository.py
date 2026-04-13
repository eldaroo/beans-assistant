"""Data-access repository for tenants and tenant metadata."""

import json
import shutil
from pathlib import Path

from tenant_manager import TenantManager, phone_to_schema_name
from database_config import db as database, USE_POSTGRES


class TenantsRepository:
    """Encapsulates tenant metadata and tenant-level DB operations."""

    def __init__(self, tenant_manager: TenantManager | None = None, db_module=database):
        self.tenant_manager = tenant_manager or TenantManager()
        self.db = db_module

    def list_tenants(self) -> list[dict]:
        return self.tenant_manager.list_tenants()

    def tenant_exists(self, phone: str) -> bool:
        return self.tenant_manager.tenant_exists(phone)

    def get_tenant_config(self, phone: str) -> dict | None:
        return self.tenant_manager.get_tenant_config(phone)

    def create_tenant(
        self,
        phone: str,
        business_name: str,
        currency: str,
        language: str,
        owner_name: str | None = None,
    ):
        self.tenant_manager.create_tenant(
            phone_number=phone,
            business_name=business_name,
            config={"currency": currency, "language": language, "owner_name": owner_name},
        )

    def create_schema_if_needed(self, phone: str):
        if USE_POSTGRES and hasattr(self.db, "create_tenant_schema"):
            self.db.create_tenant_schema(phone_to_schema_name(phone))

    def drop_schema_if_needed(self, phone: str):
        if USE_POSTGRES and hasattr(self.db, "drop_tenant_schema"):
            self.db.drop_tenant_schema(phone_to_schema_name(phone))

    def get_tenant_path(self, phone: str) -> Path:
        return self.tenant_manager.get_tenant_path(phone)

    @staticmethod
    def _registry_path() -> Path:
        return Path(__file__).resolve().parent.parent.parent / "configs" / "tenant_registry.json"

    def remove_tenant_from_registry(self, phone: str):
        if USE_POSTGRES:
            conn = self.tenant_manager._get_pg_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM public.tenants WHERE phone_number = %s", (phone,))
                conn.commit()
            finally:
                conn.close()
            return

        registry_path = self._registry_path()

        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)

        if phone in registry:
            del registry[phone]

        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)

    @staticmethod
    def delete_tenant_directory(path: Path):
        if path.exists():
            shutil.rmtree(path)

    def get_products_count(self):
        return self.db.fetch_one("SELECT COUNT(*) as count FROM products")

    def get_sales_count(self):
        return self.db.fetch_one("SELECT COUNT(*) as count FROM sales")

    def get_revenue_row(self):
        return self.db.fetch_one("SELECT total_revenue_cents FROM revenue_paid")

    def get_profit_row(self):
        return self.db.fetch_one("SELECT profit_usd FROM profit_summary")

    def get_stock_total_row(self):
        return self.db.fetch_one("SELECT COALESCE(SUM(stock_qty), 0) as total FROM stock_current")
