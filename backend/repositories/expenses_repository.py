"""Data-access repository for expenses."""

from database_config import db as database


class ExpensesRepository:
    """Encapsulates SQL/data access for expenses."""

    def __init__(self, db_module=database):
        self.db = db_module

    def list_expenses(self, limit: int, offset: int):
        query = """
            SELECT * FROM expenses
            ORDER BY expense_date DESC, created_at DESC
            LIMIT %s OFFSET %s
        """
        return self.db.fetch_all(query, (limit, offset))

    def get_expense_by_id(self, expense_id: int):
        query = "SELECT * FROM expenses WHERE id = %s"
        return self.db.fetch_one(query, (expense_id,))

    def register_expense(self, payload: dict):
        return self.db.register_expense(payload)

    def cancel_expense(self, expense_id: int):
        return self.db.cancel_expense(expense_id)
