"""
Update database views to latest version.
"""
import sqlite3

DB_PATH = "beansco.db"

def update_views():
    """Recreate views with updated schemas."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        print("Updating database views...")

        # Drop and recreate stock_current view
        print("  - Updating stock_current view...")
        cursor.execute("DROP VIEW IF EXISTS stock_current")
        cursor.execute("""
            CREATE VIEW stock_current AS
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
            GROUP BY p.id, p.sku, p.name
        """)

        conn.commit()
        print("[OK] Views updated successfully!")

        # Test the view
        print("\nTesting stock_current view:")
        cursor.execute("SELECT * FROM stock_current")
        rows = cursor.fetchall()
        for row in rows:
            print(f"  - {row[2]} ({row[1]}): {row[3]} units")

    except Exception as e:
        print(f"[ERROR] Error updating views: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    update_views()
