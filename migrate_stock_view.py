"""
Migration script: Update stock_current view to filter out inactive products.

This fixes the issue where deactivated products still appear in stock queries.
"""
import sqlite3

DB_PATH = "beansco.db"

def migrate():
    print("=" * 60)
    print("MIGRATION: Update stock_current view")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 1. Show current products (before migration)
    print("\n[BEFORE] Products in stock_current view:")
    cursor = conn.execute("SELECT name, stock_qty FROM stock_current ORDER BY name")
    for row in cursor:
        print(f"  - {row['name']}: {row['stock_qty']} unidades")

    # 2. Drop and recreate the view with is_active filter
    print("\n[MIGRATE] Recreating stock_current view with is_active filter...")

    conn.execute("DROP VIEW IF EXISTS stock_current")

    conn.execute("""
        CREATE VIEW stock_current AS
        SELECT
          p.id AS product_id,
          p.sku,
          p.name,
          COALESCE(SUM(
            CASE
              WHEN sm.movement_type IN ('IN','ADJUSTMENT') THEN sm.quantity
              WHEN sm.movement_type = 'OUT' THEN -sm.quantity
              ELSE 0
            END
          ), 0) AS stock_qty
        FROM products p
        LEFT JOIN stock_movements sm ON sm.product_id = p.id
        WHERE p.is_active = 1  -- Only show active products
        GROUP BY p.id, p.sku, p.name
    """)

    conn.commit()

    # 3. Show products after migration
    print("\n[AFTER] Products in stock_current view (only active):")
    cursor = conn.execute("SELECT name, stock_qty FROM stock_current ORDER BY name")
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  - {row['name']}: {row['stock_qty']} unidades")
    else:
        print("  (No active products with stock)")

    # 4. Show inactive products (should NOT appear in view)
    print("\n[VERIFICATION] Inactive products (should NOT be in stock_current):")
    cursor = conn.execute("""
        SELECT name, is_active
        FROM products
        WHERE is_active = 0
        ORDER BY name
    """)
    inactive = cursor.fetchall()
    if inactive:
        for row in inactive:
            print(f"  - {row['name']} (is_active={row['is_active']})")
    else:
        print("  (No inactive products)")

    conn.close()

    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE!")
    print("=" * 60)
    print("\nInactive products will no longer appear in stock queries.")

if __name__ == "__main__":
    migrate()
