"""Data-access repository for stock."""

from database_config import db as database


class StockRepository:
    """Encapsulates SQL/data access for stock."""

    def __init__(self, db_module=database):
        self.db = db_module

    def list_current_stock(self, limit: int, offset: int):
        query = """
            SELECT sc.*, p.unit_price_cents
            FROM stock_current sc
            LEFT JOIN products p ON sc.product_id = p.id
            ORDER BY sc.name
            LIMIT %s OFFSET %s
        """
        return self.db.fetch_all(query, (limit, offset))

    def list_stock_movements(self, limit: int, offset: int):
        query = """
            SELECT sm.*,
                   p.name AS product_name,
                   p.sku AS product_sku
            FROM stock_movements sm
            LEFT JOIN products p ON sm.product_id = p.id
            ORDER BY sm.occurred_at DESC, sm.created_at DESC
            LIMIT %s OFFSET %s
        """
        return self.db.fetch_all(query, (limit, offset))

    def add_stock(self, payload: dict):
        return self.db.add_stock(payload)

    def remove_stock(self, payload: dict):
        return self.db.remove_stock(payload)
