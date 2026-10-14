"""Data-access repository for the suppliers module (spec 003 M5, T-017/T-018).

SQL only; the directory shaping and the overdue-check-in arithmetic live in
``supplier_service`` (ARCHITECTURE convention: repository does SQL, service
computes). Queries use ``%s`` placeholders; the SQLite backend translates them.
Boolean columns are tested with the bare column so the same query runs on
Postgres (boolean) and SQLite (integer).
"""

from database_config import db as database


class SupplierRepository:
    """Encapsulates SQL/data access for suppliers."""

    def __init__(self, db_module=database):
        self.db = db_module

    def list_suppliers(self, active_only: bool = True):
        """All suppliers, name-ordered, with their last recorded check-in. When
        ``active_only`` the inactive ones are hidden (the directory default)."""
        where = "WHERE is_active" if active_only else ""
        query = f"""
            SELECT id, name, country, contact, is_active, last_checkin_at
            FROM suppliers
            {where}
            ORDER BY name
        """
        return self.db.fetch_all(query)

    def count_active(self) -> int:
        row = self.db.fetch_one("SELECT COUNT(*) AS n FROM suppliers WHERE is_active")
        return int(row["n"]) if row else 0

    def record_supplier(self, *, name: str, country=None, contact=None) -> int:
        """Create a supplier and return its id (the directory write path, T-017)."""
        query = """
            INSERT INTO suppliers (name, country, contact)
            VALUES (%s, %s, %s)
            RETURNING id
        """
        row = self.db.fetch_one(query, (name, country, contact))
        return int(row["id"])

    def set_checkin(self, supplier_id: int, checkin_at: str) -> None:
        """Stamp a supplier's last check-in/reply date (T-018). Stored data only;
        the overdue signal reads this. No message is sent here; the WhatsApp send
        path stays behind its named-human gate in M7."""
        self.db.execute(
            "UPDATE suppliers SET last_checkin_at = %s WHERE id = %s",
            (checkin_at, supplier_id),
        )
