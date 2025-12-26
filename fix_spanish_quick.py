"""
Arreglo rápido para hacer que las consultas en español funcionen SIN migración completa.

Este script:
1. Crea las views faltantes (stock_current, profit_summary, etc.)
2. Traduce los nombres de productos a español
3. Mantiene la estructura de tablas en inglés (compatible con código existente)
"""
import sqlite3


DB_PATH = "beansco.db"


def create_views():
    """Crea todas las views necesarias."""
    print("Creando views...")

    conn = sqlite3.connect(DB_PATH)

    # Drop views if exist (para recrearlas)
    views = [
        "stock_current",
        "profit_summary",
        "revenue_paid",
        "expenses_total",
        "sales_summary"
    ]

    for view in views:
        conn.execute(f"DROP VIEW IF EXISTS {view}")

    # Create views
    conn.executescript("""
    -- Stock actual por producto desde movimientos
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
    GROUP BY p.id, p.sku, p.name;

    -- Resumen de ventas pagadas por día
    CREATE VIEW sales_summary AS
    SELECT
      date(COALESCE(paid_at, created_at)) AS day,
      COUNT(*) AS paid_sales_count,
      SUM(total_amount_cents) AS paid_revenue_cents
    FROM sales
    WHERE status = 'PAID'
    GROUP BY date(COALESCE(paid_at, created_at))
    ORDER BY day DESC;

    -- Ingresos totales (solo ventas PAGADAS)
    CREATE VIEW revenue_paid AS
    SELECT
      SUM(total_amount_cents) AS total_revenue_cents,
      ROUND(SUM(total_amount_cents) / 100.0, 2) AS revenue_usd
    FROM sales
    WHERE status = 'PAID';

    -- Total de gastos
    CREATE VIEW expenses_total AS
    SELECT
      SUM(amount_cents) AS total_expenses_cents,
      ROUND(SUM(amount_cents) / 100.0, 2) AS expenses_usd
    FROM expenses;

    -- Resumen de ganancias (profit)
    CREATE VIEW profit_summary AS
    SELECT
      ROUND(
        (COALESCE((SELECT revenue_usd FROM revenue_paid), 0) -
         COALESCE((SELECT expenses_usd FROM expenses_total), 0)),
        2
      ) AS profit_usd;
    """)

    conn.commit()
    print("  ✓ Views creadas: stock_current, sales_summary, revenue_paid, expenses_total, profit_summary")

    # Verificar
    for view in views:
        try:
            conn.execute(f"SELECT * FROM {view} LIMIT 1")
            print(f"    ✓ {view}")
        except sqlite3.OperationalError as e:
            print(f"    ✗ {view}: {e}")

    conn.close()


def translate_products():
    """Traduce los nombres de productos a español."""
    print("\nTraduciendo nombres de productos...")

    conn = sqlite3.connect(DB_PATH)

    translations = [
        {
            "sku": "BC-BRACELET-CLASSIC",
            "name": "Pulsera de Granos de Café - Clásica",
            "description": "Pulsera artesanal con granos de café"
        },
        {
            "sku": "BC-BRACELET-BLACK",
            "name": "Pulsera de Granos de Café - Negra",
            "description": "Cordón negro, granos de café"
        },
        {
            "sku": "BC-BRACELET-GOLD",
            "name": "Pulsera de Granos de Café - Dorada",
            "description": "Acentos dorados + granos de café"
        },
        {
            "sku": "BC-KEYCHAIN",
            "name": "Llavero de Granos de Café",
            "description": "Llavero hecho con granos de café"
        }
    ]

    for product in translations:
        conn.execute(
            "UPDATE products SET name = ?, description = ? WHERE sku = ?",
            (product["name"], product["description"], product["sku"])
        )
        print(f"  ✓ {product['sku']}: {product['name']}")

    conn.commit()
    conn.close()


def verify():
    """Verifica que todo funciona."""
    print("\nVerificando...")

    conn = sqlite3.connect(DB_PATH)

    # Verificar views
    print("\nViews disponibles:")
    views = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'"
    ).fetchall()
    for view in views:
        print(f"  ✓ {view[0]}")

    # Verificar productos
    print("\nProductos actualizados:")
    products = conn.execute("SELECT sku, name FROM products").fetchall()
    for p in products:
        print(f"  • {p[0]}: {p[1]}")

    # Verificar stock
    print("\nStock actual:")
    try:
        stock = conn.execute("SELECT sku, name, stock_qty FROM stock_current").fetchall()
        for s in stock:
            print(f"  • {s[0]} ({s[1]}): {s[2]} unidades")
    except sqlite3.OperationalError as e:
        print(f"  ✗ Error al consultar stock: {e}")

    # Prueba de búsqueda en español
    print("\nPrueba: Buscar 'pulsera negra'")
    try:
        result = conn.execute(
            "SELECT sku, name, stock_qty FROM stock_current WHERE LOWER(name) LIKE '%pulsera%negra%'"
        ).fetchall()
        if result:
            for r in result:
                print(f"  ✓ Encontrado: {r[0]} ({r[1]}): {r[2]} unidades")
        else:
            print("  ⚠️  No se encontró")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    conn.close()


def main():
    print("="*70)
    print("  ARREGLO RÁPIDO: Soporte para Consultas en Español")
    print("="*70)

    # Crear backup
    print("\nCreando backup...")
    import shutil
    from datetime import datetime

    backup_path = f"beansco_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DB_PATH, backup_path)
    print(f"  ✓ Backup creado: {backup_path}")

    # Crear views
    create_views()

    # Traducir productos
    translate_products()

    # Verificar
    verify()

    print("\n" + "="*70)
    print("  ARREGLO COMPLETADO")
    print("="*70)

    print("\n✓ Cambios realizados:")
    print("  1. Views creadas (stock_current, profit_summary, etc.)")
    print("  2. Nombres de productos traducidos a español")
    print("  3. Estructura de tablas intacta (compatible con código)")

    print("\nPrueba ahora:")
    print("  python graph.py")
    print("  You> ¿cuántas pulseras negras hay?")
    print()


if __name__ == "__main__":
    main()
