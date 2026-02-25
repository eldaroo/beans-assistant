"""Data-access repository for analytics."""

from database_config import db as database


class AnalyticsRepository:
    """Encapsulates SQL/data access for analytics."""

    def __init__(self, db_module=database):
        self.db = db_module

    def get_revenue_row(self):
        return self.db.fetch_one("SELECT * FROM revenue_paid")

    def get_profit_row(self):
        return self.db.fetch_one("SELECT * FROM profit_summary")

    def get_sales_summary_rows(self, limit: int):
        query = """
            SELECT * FROM sales_summary
            ORDER BY day DESC
            LIMIT %s
        """
        return self.db.fetch_all(query, (limit,))
