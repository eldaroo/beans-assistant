"""
PostgreSQL Database Layer
Same interface as database.py but uses PostgreSQL instead of SQLite.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import os
import time
import json
import ast
from typing import Optional

# PostgreSQL connection parameters from environment
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "beansco_main")
DB_USER = os.getenv("POSTGRES_USER", "beansco")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "changeme123")
DB_SCHEMA = os.getenv("POSTGRES_SCHEMA", "public")  # For multi-tenant


def get_connection_string():
    """Build PostgreSQL connection string."""
    return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


@contextmanager
def get_conn():
    """Context manager for PostgreSQL connections."""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor  # Return rows as dicts
    )
    try:
        # Set search_path for multi-tenant support
        with conn.cursor() as cur:
            cur.execute(f"SET search_path TO {DB_SCHEMA}, public")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# =========================
# READ HELPERS
# =========================

def fetch_one(query, params=()):
    """Fetch a single row."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def fetch_all(query, params=()):
    """Fetch all rows."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


# =========================
# BUSINESS ACTIONS (WRITE)
# =========================

def register_product(data: dict):
    """Register a new product."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO products (
                      sku,
                      name,
                      description,
                      unit_price_cents,
                      unit_cost_cents
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        data["sku"],
                        data["name"],
                        data.get("description"),
                        data["unit_price_cents"],
                        data["unit_cost_cents"],
                    ),
                )

        return {
            "status": "ok",
            "sku": data["sku"],
        }
    except psycopg2.IntegrityError as e:
        error_msg = str(e)
        if "unique constraint" in error_msg.lower() and "sku" in error_msg.lower():
            print(f"[ERROR] UNIQUE constraint failed for SKU: {data['sku']}")
            print(f"[ERROR] Product name: {data['name']}")
            raise ValueError(f"El SKU '{data['sku']}' ya existe. Por favor reportá este error.")
        else:
            raise


def add_stock(data: dict):
    """
    Add stock to a product.

    data = { product_id, quantity, reason?, movement_type? }
    movement_type: IN | ADJUSTMENT (default IN)
    """
    movement_type = data.get("movement_type", "IN")
    reason = data.get("reason", "Stock update")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO stock_movements (
                    product_id,
                    movement_type,
                    quantity,
                    reason,
                    created_at
                )
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    data["product_id"],
                    movement_type,
                    data["quantity"],
                    reason,
                ),
            )

            cur.execute(
                "SELECT stock_qty FROM stock_current WHERE product_id = %s",
                (data["product_id"],),
            )
            stock = cur.fetchone()

    return {
        "status": "ok",
        "message": "Stock updated",
        "product_id": data["product_id"],
        "current_stock": stock["stock_qty"] if stock else None,
    }


def remove_stock(data: dict):
    """
    Remove stock from a product.

    data = { product_id, quantity, reason?, movement_type? }
    movement_type: OUT | ADJUSTMENT (default OUT)
    """
    movement_type = data.get("movement_type", "OUT")
    reason = data.get("reason", "Stock removal")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO stock_movements (
                    product_id,
                    movement_type,
                    quantity,
                    reason,
                    created_at
                )
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    data["product_id"],
                    movement_type,
                    data["quantity"],
                    reason,
                ),
            )

            cur.execute(
                "SELECT stock_qty FROM stock_current WHERE product_id = %s",
                (data["product_id"],),
            )
            stock = cur.fetchone()

    return {
        "status": "ok",
        "message": "Stock removed",
        "product_id": data["product_id"],
        "current_stock": stock["stock_qty"] if stock else None,
    }


def register_expense(data: dict):
    """Register a business expense."""
    amount_cents = data["amount_cents"]
    description = data.get("description", "Expense")
    category = data.get("category", "GENERAL")
    expense_date = data.get("expense_date", None)
    currency = data.get("currency", "USD")

    with get_conn() as conn:
        with conn.cursor() as cur:
            if expense_date:
                cur.execute(
                    """
                    INSERT INTO expenses (
                        expense_date,
                        category,
                        description,
                        amount_cents,
                        currency,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id
                    """,
                    (expense_date, category, description, amount_cents, currency),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO expenses (
                        category,
                        description,
                        amount_cents,
                        currency,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id
                    """,
                    (category, description, amount_cents, currency),
                )

            expense_id = cur.fetchone()["id"]

            # Get updated profit
            cur.execute("SELECT profit_usd FROM profit_summary")
            profit = cur.fetchone()

    return {
        "status": "ok",
        "expense_id": expense_id,
        "amount_usd": amount_cents / 100.0,
        "category": category,
        "profit_usd": profit["profit_usd"] if profit else None,
    }


def register_sale(data):
    """Register a new sale."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = ast.literal_eval(data)

    status = data.get("status", "PAID")
    raw_items = data["items"]

    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. Resolve product_ref → product_id
            items = []
            for item in raw_items:
                if "product_id" in item:
                    items.append(item)
                    continue

                product_ref = item.get("product_ref") or item.get("sku")
                if not product_ref:
                    raise ValueError("Each item must include product_ref or product_id")

                cur.execute(
                    """
                    SELECT id
                    FROM products
                    WHERE sku = %s
                       OR LOWER(name) LIKE '%%' || LOWER(%s) || '%%'
                    """,
                    (product_ref, product_ref),
                )

                row = cur.fetchone()
                if not row:
                    raise ValueError(f"Unknown product reference: {product_ref}")

                items.append({**item, "product_id": row["id"]})

            # 2. Validate stock
            if status == "PAID":
                for item in items:
                    cur.execute(
                        """
                        SELECT p.name, COALESCE(s.stock_qty, 0) as stock_qty
                        FROM products p
                        LEFT JOIN stock_current s ON p.id = s.product_id
                        WHERE p.id = %s
                        """,
                        (item["product_id"],),
                    )
                    product_info = cur.fetchone()

                    if not product_info:
                        raise ValueError(f"Producto con ID {item['product_id']} no encontrado")

                    product_name = product_info["name"]
                    available = product_info["stock_qty"]
                    requested = item["quantity"]

                    if available < requested:
                        raise ValueError(
                            f"No hay suficiente stock de {product_name}. "
                            f"Disponible: {available} unidades, solicitado: {requested} unidades"
                        )

            # 3. Calculate totals
            total_cents = 0
            enriched_items = []

            for item in items:
                if "unit_price_cents" in item:
                    price = item["unit_price_cents"]
                else:
                    cur.execute(
                        "SELECT unit_price_cents FROM products WHERE id = %s",
                        (item["product_id"],),
                    )
                    price = cur.fetchone()["unit_price_cents"]

                line_total = price * item["quantity"]
                total_cents += line_total
                enriched_items.append({
                    **item,
                    "unit_price_cents": price,
                    "line_total_cents": line_total
                })

            # 4. Insert sale
            sale_number = f"S-{int(time.time_ns())}"

            cur.execute(
                """
                INSERT INTO sales (sale_number, total_amount_cents, status, created_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
                """,
                (sale_number, total_cents, status),
            )
            sale_id = cur.fetchone()["id"]

            # 5. Insert items + stock movements
            for item in enriched_items:
                cur.execute(
                    """
                    INSERT INTO sale_items (sale_id, product_id, quantity, unit_price_cents, line_total_cents)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (sale_id, item["product_id"], item["quantity"], item["unit_price_cents"], item["line_total_cents"]),
                )

                if status == "PAID":
                    cur.execute(
                        """
                        INSERT INTO stock_movements
                        (product_id, movement_type, quantity, reason, created_at)
                        VALUES (%s, 'OUT', %s, 'Sale', CURRENT_TIMESTAMP)
                        """,
                        (item["product_id"], item["quantity"]),
                    )

            cur.execute("SELECT total_revenue_cents FROM revenue_paid")
            revenue = cur.fetchone()

            cur.execute("SELECT profit_usd FROM profit_summary")
            profit = cur.fetchone()

    return {
        "status": "ok",
        "sale_id": sale_id,
        "total_usd": total_cents / 100.0,
        "revenue_usd": revenue["total_revenue_cents"] / 100.0 if revenue and revenue["total_revenue_cents"] is not None else 0.0,
        "profit_usd": profit["profit_usd"] if profit and profit["profit_usd"] is not None else 0.0,
    }


# =========================
# CANCEL OPERATIONS
# =========================

def get_last_sale():
    """Get the most recent sale."""
    return fetch_one(
        """
        SELECT id, sale_number, total_amount_cents, status, created_at
        FROM sales
        ORDER BY created_at DESC
        LIMIT 1
        """
    )


def get_last_expense():
    """Get the most recent expense."""
    return fetch_one(
        """
        SELECT id, description, amount_cents, category, expense_date, created_at
        FROM expenses
        ORDER BY created_at DESC
        LIMIT 1
        """
    )


def get_last_stock_movement():
    """Get the most recent stock movement (IN or ADJUSTMENT only, not sales)."""
    return fetch_one(
        """
        SELECT sm.id, sm.product_id, sm.quantity, sm.reason, sm.movement_type,
               sm.created_at, p.name as product_name, p.sku
        FROM stock_movements sm
        JOIN products p ON sm.product_id = p.id
        WHERE sm.movement_type IN ('IN', 'ADJUSTMENT')
        ORDER BY sm.created_at DESC
        LIMIT 1
        """
    )


def get_last_operation():
    """Get the most recent operation (sale, expense, or stock movement)."""
    last_sale = get_last_sale()
    last_expense = get_last_expense()
    last_stock = get_last_stock_movement()

    operations = []

    if last_sale:
        operations.append({
            "type": "SALE",
            "timestamp": last_sale["created_at"],
            "data": last_sale
        })

    if last_expense:
        operations.append({
            "type": "EXPENSE",
            "timestamp": last_expense["created_at"],
            "data": last_expense
        })

    if last_stock:
        operations.append({
            "type": "STOCK",
            "timestamp": last_stock["created_at"],
            "data": last_stock
        })

    if not operations:
        return None

    # Sort by timestamp and get the most recent
    operations.sort(key=lambda x: x["timestamp"], reverse=True)
    return operations[0]


def cancel_sale(sale_id: int):
    """Cancel a sale and restore stock."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get sale details
            cur.execute(
                "SELECT id, sale_number, total_amount_cents, status FROM sales WHERE id = %s",
                (sale_id,)
            )
            sale = cur.fetchone()

            if not sale:
                raise ValueError(f"Venta con ID {sale_id} no encontrada")

            # Get sale items
            cur.execute(
                """
                SELECT product_id, quantity, unit_price_cents
                FROM sale_items
                WHERE sale_id = %s
                """,
                (sale_id,)
            )
            items = cur.fetchall()

            # If sale was PAID, restore stock
            if sale["status"] == "PAID":
                for item in items:
                    cur.execute(
                        """
                        INSERT INTO stock_movements
                        (product_id, movement_type, quantity, reason, created_at)
                        VALUES (%s, 'IN', %s, 'Venta cancelada', CURRENT_TIMESTAMP)
                        """,
                        (item["product_id"], item["quantity"]),
                    )

            # Delete sale items
            cur.execute("DELETE FROM sale_items WHERE sale_id = %s", (sale_id,))

            # Delete sale
            cur.execute("DELETE FROM sales WHERE id = %s", (sale_id,))

            # Get updated stats
            cur.execute("SELECT total_revenue_cents FROM revenue_paid")
            revenue = cur.fetchone()

            cur.execute("SELECT profit_usd FROM profit_summary")
            profit = cur.fetchone()

    return {
        "status": "ok",
        "sale_number": sale["sale_number"],
        "cancelled_amount": sale["total_amount_cents"] / 100.0,
        "revenue_usd": revenue["total_revenue_cents"] / 100.0 if revenue and revenue["total_revenue_cents"] is not None else 0.0,
        "profit_usd": profit["profit_usd"] if profit and profit["profit_usd"] is not None else 0.0,
    }


def cancel_expense(expense_id: int):
    """Cancel an expense."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get expense details
            cur.execute(
                "SELECT id, description, amount_cents FROM expenses WHERE id = %s",
                (expense_id,)
            )
            expense = cur.fetchone()

            if not expense:
                raise ValueError(f"Gasto con ID {expense_id} no encontrado")

            # Delete expense
            cur.execute("DELETE FROM expenses WHERE id = %s", (expense_id,))

            # Get updated profit
            cur.execute("SELECT profit_usd FROM profit_summary")
            profit = cur.fetchone()

    return {
        "status": "ok",
        "description": expense["description"],
        "cancelled_amount": expense["amount_cents"] / 100.0,
        "profit_usd": profit["profit_usd"] if profit else 0,
    }


def cancel_stock_movement(movement_id: int):
    """Cancel a stock movement by creating an inverse movement."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get movement details
            cur.execute(
                """
                SELECT sm.id, sm.product_id, sm.quantity, sm.reason, sm.movement_type,
                       p.name as product_name, p.sku
                FROM stock_movements sm
                JOIN products p ON sm.product_id = p.id
                WHERE sm.id = %s
                """,
                (movement_id,)
            )
            movement = cur.fetchone()

            if not movement:
                raise ValueError(f"Movimiento de stock con ID {movement_id} no encontrado")

            # Can only cancel IN or ADJUSTMENT movements (not sales)
            if movement["movement_type"] not in ["IN", "ADJUSTMENT"]:
                raise ValueError(f"Solo se pueden cancelar movimientos de tipo IN o ADJUSTMENT")

            # Create inverse movement
            cur.execute(
                """
                INSERT INTO stock_movements
                (product_id, movement_type, quantity, reason, created_at)
                VALUES (%s, 'ADJUSTMENT', %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    movement["product_id"],
                    -movement["quantity"],  # Negative to reverse
                    f"Cancelación de: {movement['reason']}"
                )
            )

            # Get updated stock
            cur.execute(
                "SELECT stock_qty FROM stock_current WHERE product_id = %s",
                (movement["product_id"],)
            )
            stock = cur.fetchone()

    return {
        "status": "ok",
        "product_name": movement["product_name"],
        "sku": movement["sku"],
        "cancelled_quantity": movement["quantity"],
        "current_stock": stock["stock_qty"] if stock else 0,
    }


def deactivate_product(product_id: int):
    """Deactivate a product (mark as inactive, don't delete)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get product details
            cur.execute(
                "SELECT id, sku, name, is_active FROM products WHERE id = %s",
                (product_id,)
            )
            product = cur.fetchone()

            if not product:
                raise ValueError(f"Producto con ID {product_id} no encontrado")

            if not product["is_active"]:
                raise ValueError(f"El producto '{product['name']}' ya está desactivado")

            # Mark as inactive
            cur.execute(
                "UPDATE products SET is_active = FALSE WHERE id = %s",
                (product_id,)
            )

            print(f"[Deactivate Product] Desactivado: {product['name']} (SKU: {product['sku']})")

    return {
        "status": "ok",
        "product_id": product_id,
        "sku": product["sku"],
        "name": product["name"],
    }
