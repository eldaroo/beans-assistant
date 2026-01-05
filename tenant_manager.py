"""
Tenant Manager - Gestión de clientes multi-tenant.

Cada cliente tiene:
- Su propia base de datos
- Configuración personalizada
- Prompts customizados
"""
import os
import json
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class TenantManager:
    """Gestiona múltiples clientes (tenants) con bases de datos separadas."""

    def __init__(self, base_path: str = "data/clients"):
        """
        Initialize tenant manager.

        Args:
            base_path: Base directory for client data
        """
        self.base_path = Path(base_path)
        self.registry_path = Path("configs/tenant_registry.json")
        self.templates_path = Path("data/templates")

        # Create directories if they don't exist
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.templates_path.mkdir(parents=True, exist_ok=True)

        # Load tenant registry
        self.registry = self._load_registry()

    def _load_registry(self) -> Dict[str, Any]:
        """Load tenant registry from disk."""
        if self.registry_path.exists():
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_registry(self):
        """Save tenant registry to disk."""
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)

    def tenant_exists(self, phone_number: str) -> bool:
        """
        Check if a tenant exists.

        Args:
            phone_number: Phone number (e.g., "+5491112345678")

        Returns:
            True if tenant exists
        """
        return phone_number in self.registry

    def get_tenant_path(self, phone_number: str) -> Path:
        """Get the directory path for a tenant."""
        return self.base_path / phone_number

    def get_tenant_db_path(self, phone_number: str) -> str:
        """Get the database path for a tenant."""
        return str(self.get_tenant_path(phone_number) / "business.db")

    def get_tenant_config(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """
        Get tenant configuration.

        Args:
            phone_number: Phone number

        Returns:
            Config dict or None if not found
        """
        if not self.tenant_exists(phone_number):
            return None

        config_path = self.get_tenant_path(phone_number) / "config.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def create_tenant(
        self,
        phone_number: str,
        business_name: str,
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Create a new tenant with their own database and config.

        Args:
            phone_number: Phone number (unique identifier)
            business_name: Name of the business
            config: Optional custom configuration

        Returns:
            True if created successfully
        """
        if self.tenant_exists(phone_number):
            print(f"[TENANT] Tenant {phone_number} already exists")
            return False

        print(f"[TENANT] Creating new tenant: {phone_number} ({business_name})")

        # Create tenant directory
        tenant_path = self.get_tenant_path(phone_number)
        tenant_path.mkdir(parents=True, exist_ok=True)

        # Create database
        db_path = self.get_tenant_db_path(phone_number)
        self._create_database(db_path)

        # Create config
        if config is None:
            config = self._get_default_config()

        config["business_name"] = business_name
        config["phone_number"] = phone_number
        config["created_at"] = datetime.now().isoformat()

        config_path = tenant_path / "config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # Register tenant
        self.registry[phone_number] = {
            "business_name": business_name,
            "created_at": datetime.now().isoformat(),
            "status": "active"
        }
        self._save_registry()

        print(f"[TENANT] [OK] Tenant created successfully")
        return True

    def _create_database(self, db_path: str):
        """Create a new database with default schema."""
        print(f"[TENANT] Creating database: {db_path}")

        # Load default schema
        schema_template = self.templates_path / "default_schema.sql"
        if schema_template.exists():
            with open(schema_template, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
        else:
            # Use embedded default schema
            schema_sql = self._get_default_schema()

        # Create database and execute schema
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(schema_sql)
            conn.commit()
            print(f"[TENANT] [OK] Database created")
        finally:
            conn.close()

    def _get_default_schema(self) -> str:
        """Get default database schema."""
        return """
-- Products table
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    unit_cost_cents INTEGER NOT NULL DEFAULT 0,
    unit_price_cents INTEGER NOT NULL,
    is_active INTEGER DEFAULT 1 NOT NULL,
    created_at TEXT DEFAULT (datetime('now')) NOT NULL,
    CHECK (unit_cost_cents >= 0),
    CHECK (unit_price_cents >= 0)
);

-- Sales table
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_number TEXT NOT NULL UNIQUE,
    customer_name TEXT,
    status TEXT NOT NULL CHECK (status IN ('PAID','PENDING','CANCELLED')),
    currency TEXT DEFAULT 'USD' NOT NULL,
    total_amount_cents INTEGER NOT NULL CHECK (total_amount_cents >= 0),
    created_at TEXT DEFAULT (datetime('now')) NOT NULL,
    paid_at TEXT
);

-- Sale items table
CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL,
    line_total_cents INTEGER NOT NULL,
    FOREIGN KEY(sale_id) REFERENCES sales(id),
    FOREIGN KEY(product_id) REFERENCES products(id)
);

-- Stock movements table
CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    movement_type TEXT NOT NULL CHECK (movement_type IN ('IN','OUT','ADJUSTMENT')),
    quantity INTEGER NOT NULL CHECK (quantity <> 0),
    reason TEXT,
    reference TEXT,
    occurred_at TEXT DEFAULT (datetime('now')) NOT NULL,
    created_at TEXT DEFAULT (datetime('now')) NOT NULL,
    FOREIGN KEY(product_id) REFERENCES products(id)
);

-- Expenses table
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_date TEXT DEFAULT (date('now')) NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    currency TEXT DEFAULT 'USD' NOT NULL,
    created_at TEXT DEFAULT (datetime('now')) NOT NULL
);

-- Views
CREATE VIEW IF NOT EXISTS revenue_paid AS
SELECT COALESCE(SUM(total_amount_cents), 0) AS total_revenue_cents
FROM sales WHERE status = 'PAID';

CREATE VIEW IF NOT EXISTS expenses_total AS
SELECT COALESCE(SUM(amount_cents), 0) AS total_expenses_cents FROM expenses;

CREATE VIEW IF NOT EXISTS profit_summary AS
SELECT (r.total_revenue_cents - e.total_expenses_cents) / 100.0 AS profit_usd
FROM revenue_paid r, expenses_total e;

CREATE VIEW IF NOT EXISTS stock_current AS
SELECT
  p.id AS product_id,
  p.sku,
  p.name,
  COALESCE(
    SUM(
      CASE
        WHEN sm.movement_type IN ('IN', 'ADJUSTMENT') THEN sm.quantity
        WHEN sm.movement_type = 'OUT' THEN -sm.quantity
        ELSE 0
      END
    ),
    0
  ) AS stock_qty
FROM products p
LEFT JOIN stock_movements sm ON p.id = sm.product_id
WHERE p.is_active = 1
GROUP BY p.id, p.sku, p.name;
"""

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default tenant configuration."""
        return {
            "business_name": "",
            "phone_number": "",
            "language": "es",
            "currency": "USD",
            "timezone": "America/Argentina/Buenos_Aires",
            "prompts": {
                "system_prompt": "Eres un asistente de negocios inteligente.",
                "welcome_message": "¡Hola! Soy tu asistente de negocios. ¿En qué puedo ayudarte?"
            },
            "features": {
                "audio_enabled": True,
                "sales_enabled": True,
                "expenses_enabled": True,
                "inventory_enabled": True
            }
        }

    def list_tenants(self) -> Dict[str, Any]:
        """List all registered tenants."""
        return self.registry

    def get_tenant_stats(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a tenant."""
        if not self.tenant_exists(phone_number):
            return None

        db_path = self.get_tenant_db_path(phone_number)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        try:
            stats = {}

            # Product count
            result = conn.execute("SELECT COUNT(*) as count FROM products").fetchone()
            stats["products"] = result["count"]

            # Sales count
            result = conn.execute("SELECT COUNT(*) as count FROM sales").fetchone()
            stats["sales"] = result["count"]

            # Revenue
            result = conn.execute("SELECT total_revenue_cents FROM revenue_paid").fetchone()
            stats["revenue_usd"] = result["total_revenue_cents"] / 100.0 if result else 0

            # Profit
            result = conn.execute("SELECT profit_usd FROM profit_summary").fetchone()
            stats["profit_usd"] = result["profit_usd"] if result else 0

            return stats

        finally:
            conn.close()


# Global instance
_tenant_manager: Optional[TenantManager] = None


def get_tenant_manager() -> TenantManager:
    """Get or create global TenantManager instance."""
    global _tenant_manager
    if _tenant_manager is None:
        _tenant_manager = TenantManager()
    return _tenant_manager
