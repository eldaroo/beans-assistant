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

    def get_today_sales_counts_row(self):
        """Count today's sales by state for the Hoy daily-truth headline
        (spec 006 T-010). One cheap aggregate over the sales table, keyed on
        the sale's creation date so the sentence reflects the owner's day. A
        half-open range on created_at (not a ``::date`` cast) so any index on
        created_at can serve the scan. NOTE: CURRENT_DATE is the DB server's
        timezone, so near midnight the "today" boundary can be off by a day for
        a tenant in another timezone; a tenant-timezone-aware boundary is a
        follow-on (the owner spans three countries). The CHECK on sales.status
        makes the two buckets exhaustive of the active (non-cancelled) states."""
        query = """
            SELECT
                COUNT(*) FILTER (WHERE status = 'PAID')    AS paid_today,
                COUNT(*) FILTER (WHERE status = 'PENDING') AS unpaid_today
            FROM sales
            WHERE created_at >= CURRENT_DATE
              AND created_at <  CURRENT_DATE + INTERVAL '1 day'
        """
        return self.db.fetch_one(query)
