"""Data-access repository for products."""

from typing import Any

from database_config import db as database


PRODUCT_COLUMNS = (
    "id, sku, name, description, unit_cost_cents, unit_price_cents, is_active, created_at"
)


class ProductsRepository:
    """Encapsulates SQL/data access for products."""

    def __init__(self, db_module=database):
        self.db = db_module

    def list_products(self, include_inactive: bool, limit: int, offset: int) -> list[dict]:
        if include_inactive:
            query = f"""
                SELECT {PRODUCT_COLUMNS}
                FROM products
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            return self.db.fetch_all(query, (limit, offset))

        query = f"""
            SELECT {PRODUCT_COLUMNS}
            FROM products
            WHERE is_active = TRUE
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        return self.db.fetch_all(query, (limit, offset))

    def get_by_id(self, product_id: int):
        query = f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id = %s"
        return self.db.fetch_one(query, (product_id,))

    def get_by_sku(self, sku: str):
        query = f"SELECT {PRODUCT_COLUMNS} FROM products WHERE sku = %s"
        return self.db.fetch_one(query, (sku,))

    def create(self, payload: dict):
        params = (
            payload["sku"],
            payload["name"],
            payload.get("description"),
            payload["unit_cost_cents"],
            payload["unit_price_cents"],
        )
        query = f"""
            INSERT INTO products (
                sku,
                name,
                description,
                unit_cost_cents,
                unit_price_cents
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING {PRODUCT_COLUMNS}
        """
        return self.db.fetch_one(query, params)

    def create_without_returning(self, payload: dict):
        params = (
            payload["sku"],
            payload["name"],
            payload.get("description"),
            payload["unit_cost_cents"],
            payload["unit_price_cents"],
        )
        query = """
            INSERT INTO products (
                sku,
                name,
                description,
                unit_cost_cents,
                unit_price_cents
            )
            VALUES (%s, %s, %s, %s, %s)
        """
        self.db.execute(query, params)

    def update(self, product_id: int, updates: dict[str, Any]):
        if not updates:
            return self.get_by_id(product_id)

        fields = []
        params: list[Any] = []
        for key, value in updates.items():
            fields.append(f"{key} = %s")
            params.append(value)
        params.append(product_id)

        query = f"""
            UPDATE products
            SET {", ".join(fields)}
            WHERE id = %s
            RETURNING {PRODUCT_COLUMNS}
        """
        return self.db.fetch_one(query, tuple(params))

    def update_without_returning(self, product_id: int, updates: dict[str, Any]):
        if not updates:
            return self.get_by_id(product_id)

        fields = []
        params: list[Any] = []
        for key, value in updates.items():
            fields.append(f"{key} = %s")
            params.append(value)
        params.append(product_id)

        query = f"""
            UPDATE products
            SET {", ".join(fields)}
            WHERE id = %s
        """
        self.db.execute(query, tuple(params))
        return self.get_by_id(product_id)

    def deactivate(self, product_id: int):
        return self.db.deactivate_product(product_id)

