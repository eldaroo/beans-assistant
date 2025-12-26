"""
Script de migración: Base de datos de Inglés a Español

Este script migra la base de datos actual (inglés) a una nueva con nombres en español.
Preserva todos los datos existentes.
"""
import sqlite3
import os
from datetime import datetime


DB_OLD = "beansco.db"
DB_NEW = "beansco_es.db"
DB_BACKUP = f"beansco_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"


def backup_database():
    """Crea un backup de la base de datos actual."""
    if os.path.exists(DB_OLD):
        print(f"Creando backup: {DB_BACKUP}")
        import shutil
        shutil.copy2(DB_OLD, DB_BACKUP)
        print(f"✓ Backup creado: {DB_BACKUP}")
    else:
        print(f"⚠️  No se encontró {DB_OLD}")


def create_spanish_schema():
    """Crea el nuevo schema en español."""
    print(f"\nCreando nueva base de datos: {DB_NEW}")

    # Leer el schema en español
    with open("schema_spanish.sql", "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Crear nueva BD
    conn = sqlite3.connect(DB_NEW)
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()

    print(f"✓ Base de datos creada: {DB_NEW}")


def migrate_data():
    """Migra los datos de la BD antigua a la nueva."""
    print("\nMigrando datos...")

    if not os.path.exists(DB_OLD):
        print(f"⚠️  No se encontró {DB_OLD}, usando datos de ejemplo del schema")
        return

    conn_old = sqlite3.connect(DB_OLD)
    conn_old.row_factory = sqlite3.Row
    conn_new = sqlite3.connect(DB_NEW)

    try:
        # Limpiar datos de ejemplo
        print("  Limpiando datos de ejemplo...")
        conn_new.execute("DELETE FROM items_venta")
        conn_new.execute("DELETE FROM ventas")
        conn_new.execute("DELETE FROM movimientos_stock")
        conn_new.execute("DELETE FROM gastos")
        conn_new.execute("DELETE FROM productos")

        # Migrar productos
        print("  Migrando productos...")
        productos = conn_old.execute("SELECT * FROM products").fetchall()
        for p in productos:
            # Traducir nombre del producto
            nombre = p["name"]
            nombre = nombre.replace("Coffee Bean Bracelet", "Pulsera de Granos de Café")
            nombre = nombre.replace("Coffee Bean Keychain", "Llavero de Granos de Café")
            nombre = nombre.replace("Classic", "Clásica")
            nombre = nombre.replace("Black", "Negra")
            nombre = nombre.replace("Gold", "Dorada")

            descripcion = p["description"] or ""
            descripcion = descripcion.replace("Handmade bracelet with coffee beans", "Pulsera artesanal con granos de café")
            descripcion = descripcion.replace("Black cord, coffee beans", "Cordón negro, granos de café")
            descripcion = descripcion.replace("Gold accents + coffee beans", "Acentos dorados + granos de café")
            descripcion = descripcion.replace("Keychain made with coffee beans", "Llavero hecho con granos de café")

            conn_new.execute(
                """
                INSERT INTO productos (id, sku, nombre, descripcion, costo_unitario_centavos,
                                      precio_unitario_centavos, esta_activo, creado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (p["id"], p["sku"], nombre, descripcion, p["unit_cost_cents"],
                 p["unit_price_cents"], p["is_active"], p["created_at"])
            )
        print(f"    ✓ {len(productos)} productos migrados")

        # Migrar movimientos de stock
        print("  Migrando movimientos de stock...")
        movements = conn_old.execute("SELECT * FROM stock_movements").fetchall()
        for m in movements:
            tipo = m["movement_type"]
            tipo = {"IN": "ENTRADA", "OUT": "SALIDA", "ADJUSTMENT": "AJUSTE"}.get(tipo, tipo)

            razon = m["reason"] or ""
            razon = razon.replace("Initial stock", "Stock inicial")
            razon = razon.replace("Sale", "Venta")
            razon = razon.replace("Stock update", "Actualización de stock")

            conn_new.execute(
                """
                INSERT INTO movimientos_stock (id, producto_id, tipo_movimiento, cantidad,
                                               razon, referencia, ocurrido_en, creado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (m["id"], m["product_id"], tipo, m["quantity"], razon,
                 m["reference"], m["occurred_at"], m["created_at"])
            )
        print(f"    ✓ {len(movements)} movimientos migrados")

        # Migrar gastos
        print("  Migrando gastos...")
        expenses = conn_old.execute("SELECT * FROM expenses").fetchall()
        for e in expenses:
            categoria = e["category"]
            categoria = categoria.replace("Materials", "Materiales")
            categoria = categoria.replace("Packaging", "Empaque")
            categoria = categoria.replace("Marketing", "Marketing")
            categoria = categoria.replace("Shipping", "Envíos")
            categoria = categoria.replace("GENERAL", "GENERAL")

            descripcion = e["description"] or ""
            descripcion = descripcion.replace("Coffee beans batch", "Lote de granos de café")
            descripcion = descripcion.replace("Boxes and labels", "Cajas y etiquetas")
            descripcion = descripcion.replace("Instagram ads", "Anuncios en Instagram")
            descripcion = descripcion.replace("Courier account top-up", "Recarga de cuenta de mensajería")

            conn_new.execute(
                """
                INSERT INTO gastos (id, fecha_gasto, categoria, descripcion,
                                   monto_centavos, moneda, creado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (e["id"], e["expense_date"], categoria, descripcion,
                 e["amount_cents"], e["currency"], e["created_at"])
            )
        print(f"    ✓ {len(expenses)} gastos migrados")

        # Migrar ventas
        print("  Migrando ventas...")
        sales = conn_old.execute("SELECT * FROM sales").fetchall()
        for s in sales:
            estado = s["status"]
            estado = {"PAID": "PAGADO", "PENDING": "PENDIENTE", "CANCELLED": "CANCELADO"}.get(estado, estado)

            numero = s["sale_number"].replace("S-", "V-")  # S de Sale → V de Venta

            conn_new.execute(
                """
                INSERT INTO ventas (id, numero_venta, nombre_cliente, estado, moneda,
                                   monto_total_centavos, creado_en, pagado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (s["id"], numero, s["customer_name"], estado, s["currency"],
                 s["total_amount_cents"], s["created_at"], s["paid_at"])
            )
        print(f"    ✓ {len(sales)} ventas migradas")

        # Migrar items de venta
        print("  Migrando items de venta...")
        items = conn_old.execute("SELECT * FROM sale_items").fetchall()
        for i in items:
            conn_new.execute(
                """
                INSERT INTO items_venta (id, venta_id, producto_id, cantidad,
                                        precio_unitario_centavos, total_linea_centavos, creado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (i["id"], i["sale_id"], i["product_id"], i["quantity"],
                 i["unit_price_cents"], i["line_total_cents"], i["created_at"])
            )
        print(f"    ✓ {len(items)} items migrados")

        conn_new.commit()
        print("\n✓ Migración completada exitosamente")

    except Exception as e:
        print(f"\n✗ Error durante la migración: {e}")
        import traceback
        traceback.print_exc()
        conn_new.rollback()
    finally:
        conn_old.close()
        conn_new.close()


def verify_migration():
    """Verifica que la migración fue exitosa."""
    print("\nVerificando migración...")

    conn = sqlite3.connect(DB_NEW)

    # Verificar tablas
    tables = ["productos", "movimientos_stock", "gastos", "ventas", "items_venta"]
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  ✓ {table}: {count} registros")

    # Verificar views
    views = ["stock_actual", "resumen_ventas", "ingresos_pagados", "total_gastos", "resumen_ganancias"]
    for view in views:
        try:
            conn.execute(f"SELECT * FROM {view} LIMIT 1")
            print(f"  ✓ Vista {view} existe")
        except sqlite3.OperationalError as e:
            print(f"  ✗ Vista {view} falta: {e}")

    # Mostrar ejemplo de productos
    print("\nEjemplo de productos migrados:")
    productos = conn.execute("SELECT sku, nombre FROM productos LIMIT 3").fetchall()
    for p in productos:
        print(f"  • {p[0]}: {p[1]}")

    # Mostrar stock actual
    print("\nStock actual:")
    stock = conn.execute("SELECT sku, nombre, cantidad_stock FROM stock_actual").fetchall()
    for s in stock:
        print(f"  • {s[0]} ({s[1]}): {s[2]} unidades")

    conn.close()


def main():
    """Ejecuta la migración completa."""
    print("="*70)
    print("  MIGRACIÓN DE BASE DE DATOS: INGLÉS → ESPAÑOL")
    print("="*70)

    # Paso 1: Backup
    backup_database()

    # Paso 2: Crear nuevo schema
    create_spanish_schema()

    # Paso 3: Migrar datos
    migrate_data()

    # Paso 4: Verificar
    verify_migration()

    print("\n" + "="*70)
    print("  MIGRACIÓN COMPLETADA")
    print("="*70)
    print(f"\nArchivos:")
    print(f"  • Base de datos antigua: {DB_OLD}")
    print(f"  • Backup creado: {DB_BACKUP}")
    print(f"  • Nueva base de datos: {DB_NEW}")
    print(f"\nPara usar la nueva base de datos en español:")
    print(f"  1. Renombrar: mv {DB_OLD} {DB_OLD}.old")
    print(f"  2. Activar: mv {DB_NEW} {DB_OLD}")
    print(f"  O directamente: mv {DB_NEW} {DB_OLD}")
    print(f"\nPara probar:")
    print(f"  python graph.py --db sqlite:///{DB_NEW}")
    print()


if __name__ == "__main__":
    main()
