"""Data-access repository for sales."""

from database_config import db as database


class SalesRepository:
    """Encapsulates SQL/data access for sales."""

    def __init__(self, db_module=database):
        self.db = db_module

    def list_sales(self, limit: int, offset: int):
        query = """
            SELECT * FROM sales
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        return self.db.fetch_all(query, (limit, offset))

    def get_sale_by_id(self, sale_id: int):
        query = "SELECT * FROM sales WHERE id = %s"
        return self.db.fetch_one(query, (sale_id,))

    def list_sale_items(self, sale_id: int):
        query = """
            SELECT si.*,
                   p.name AS product_name,
                   p.sku AS product_sku
            FROM sale_items si
            LEFT JOIN products p ON si.product_id = p.id
            WHERE si.sale_id = %s
        """
        return self.db.fetch_all(query, (sale_id,))

    def register_sale(self, payload: dict):
        return self.db.register_sale(payload)

    def cancel_sale(self, sale_id: int):
        return self.db.cancel_sale(sale_id)
