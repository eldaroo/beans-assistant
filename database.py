import sqlite3
from contextlib import contextmanager
import time
import json
import ast

DB_PATH = "beansco.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
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
    with get_conn() as conn:
        cur = conn.execute(query, params)
        return cur.fetchone()


def fetch_all(query, params=()):
    with get_conn() as conn:
        cur = conn.execute(query, params)
        return cur.fetchall()


# =========================
# BUSINESS ACTIONS (WRITE)
# =========================

def register_product(data: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO products (
              sku,
              name,
              description,
              unit_price_cents,
              unit_cost_cents
            )
            VALUES (?, ?, ?, ?, ?)
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

def add_stock(data: dict):
    """
    data = { product_id, quantity, reason?, movement_type? }
    movement_type: IN | ADJUSTMENT (default IN)
    """
    movement_type = data.get("movement_type", "IN")
    reason = data.get("reason", "Stock update")

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO stock_movements (
                product_id,
                movement_type,
                quantity,
                reason,
                created_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                data["product_id"],
                movement_type,
                data["quantity"],
                reason,
            ),
        )

        stock = conn.execute(
            "SELECT stock_qty FROM stock_current WHERE product_id = ?",
            (data["product_id"],),
        ).fetchone()

    return {
        "status": "ok",
        "message": "Stock updated",
        "product_id": data["product_id"],
        "current_stock": stock["stock_qty"] if stock else None,
    }


def register_expense(data: dict):
    """
    Register a business expense.

    data = {
        amount_cents: int (required),
        description: str (required),
        category: str (default: GENERAL),
        expense_date: str (ISO date, default: today),
        currency: str (default: USD)
    }
    """
    amount_cents = data["amount_cents"]
    description = data.get("description", "Expense")
    category = data.get("category", "GENERAL")
    expense_date = data.get("expense_date", None)
    currency = data.get("currency", "USD")

    with get_conn() as conn:
        if expense_date:
            expense_id = conn.execute(
                """
                INSERT INTO expenses (
                    expense_date,
                    category,
                    description,
                    amount_cents,
                    currency,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (expense_date, category, description, amount_cents, currency),
            ).lastrowid
        else:
            expense_id = conn.execute(
                """
                INSERT INTO expenses (
                    category,
                    description,
                    amount_cents,
                    currency,
                    created_at
                )
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (category, description, amount_cents, currency),
            ).lastrowid

        # Get updated profit
        profit = conn.execute(
            "SELECT profit_usd FROM profit_summary"
        ).fetchone()

    return {
        "status": "ok",
        "expense_id": expense_id,
        "amount_usd": amount_cents / 100.0,
        "category": category,
        "profit_usd": profit["profit_usd"] if profit else None,
    }


def register_sale(data):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = ast.literal_eval(data)

    status = data.get("status", "PAID")
    raw_items = data["items"]

    with get_conn() as conn:

        # 1. Resolve product_ref → product_id
        items = []
        for item in raw_items:
            if "product_id" in item:
                items.append(item)
                continue

            product_ref = item.get("product_ref") or item.get("sku")
            if not product_ref:
                raise ValueError("Each item must include product_ref or product_id")

            row = conn.execute(
                """
                SELECT id
                FROM products
                WHERE sku = ?
                   OR LOWER(name) LIKE '%' || LOWER(?) || '%'
                """,
                (product_ref, product_ref),
            ).fetchone()

            if not row:
                raise ValueError(f"Unknown product reference: {product_ref}")

            items.append({**item, "product_id": row["id"]})

        # 2. Validate stock
        if status == "PAID":
            for item in items:
                # Get product name and stock
                product_info = conn.execute(
                    """
                    SELECT p.name, COALESCE(s.stock_qty, 0) as stock_qty
                    FROM products p
                    LEFT JOIN stock_current s ON p.id = s.product_id
                    WHERE p.id = ?
                    """,
                    (item["product_id"],),
                ).fetchone()

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
                price = conn.execute(
                    "SELECT unit_price_cents FROM products WHERE id = ?",
                    (item["product_id"],),
                ).fetchone()["unit_price_cents"]

            line_total = price * item["quantity"]
            total_cents += line_total
            enriched_items.append({
                **item,
                "unit_price_cents": price,
                "line_total_cents": line_total
            })

        # 4. Insert sale
        sale_number = f"S-{int(time.time())}"

        sale_id = conn.execute(
            """
            INSERT INTO sales (sale_number, total_amount_cents, status, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (sale_number, total_cents, status),
        ).lastrowid

        # 5. Insert items + stock movements
        for item in enriched_items:
            conn.execute(
                """
                INSERT INTO sale_items (sale_id, product_id, quantity, unit_price_cents, line_total_cents)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sale_id, item["product_id"], item["quantity"], item["unit_price_cents"], item["line_total_cents"]),
            )

            if status == "PAID":
                conn.execute(
                    """
                    INSERT INTO stock_movements
                    (product_id, movement_type, quantity, reason, created_at)
                    VALUES (?, 'OUT', ?, 'Sale', CURRENT_TIMESTAMP)
                    """,
                    (item["product_id"], item["quantity"]),
                )

        revenue = conn.execute(
            "SELECT total_revenue_cents FROM revenue_paid"
        ).fetchone()

        profit = conn.execute(
            "SELECT profit_usd FROM profit_summary"
        ).fetchone()

    # ⬅️ acá ya está cerrada la conexión, pero no la usamos más

    return {
        "status": "ok",
        "sale_id": sale_id,
        "total_usd": total_cents / 100.0,
        "revenue_usd": revenue["total_revenue_cents"] / 100.0 if revenue else None,
        "profit_usd": profit["profit_usd"] if profit else None,
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


def cancel_sale(sale_id: int):
    """
    Cancel a sale and restore stock.

    Args:
        sale_id: ID of the sale to cancel

    Returns:
        Dict with cancellation result
    """
    with get_conn() as conn:
        # Get sale details
        sale = conn.execute(
            "SELECT id, sale_number, total_amount_cents, status FROM sales WHERE id = ?",
            (sale_id,)
        ).fetchone()

        if not sale:
            raise ValueError(f"Venta con ID {sale_id} no encontrada")

        # Get sale items
        items = conn.execute(
            """
            SELECT product_id, quantity, unit_price_cents
            FROM sale_items
            WHERE sale_id = ?
            """,
            (sale_id,)
        ).fetchall()

        # If sale was PAID, restore stock
        if sale["status"] == "PAID":
            for item in items:
                # Add stock back (reverse the OUT movement)
                conn.execute(
                    """
                    INSERT INTO stock_movements
                    (product_id, movement_type, quantity, reason, created_at)
                    VALUES (?, 'IN', ?, 'Venta cancelada', CURRENT_TIMESTAMP)
                    """,
                    (item["product_id"], item["quantity"]),
                )

        # Delete sale items
        conn.execute("DELETE FROM sale_items WHERE sale_id = ?", (sale_id,))

        # Delete sale
        conn.execute("DELETE FROM sales WHERE id = ?", (sale_id,))

        # Get updated stats
        revenue = conn.execute("SELECT total_revenue_cents FROM revenue_paid").fetchone()
        profit = conn.execute("SELECT profit_usd FROM profit_summary").fetchone()

    return {
        "status": "ok",
        "sale_number": sale["sale_number"],
        "cancelled_amount": sale["total_amount_cents"] / 100.0,
        "revenue_usd": revenue["total_revenue_cents"] / 100.0 if revenue else 0,
        "profit_usd": profit["profit_usd"] if profit else 0,
    }


def cancel_expense(expense_id: int):
    """
    Cancel an expense.

    Args:
        expense_id: ID of the expense to cancel

    Returns:
        Dict with cancellation result
    """
    with get_conn() as conn:
        # Get expense details
        expense = conn.execute(
            "SELECT id, description, amount_cents FROM expenses WHERE id = ?",
            (expense_id,)
        ).fetchone()

        if not expense:
            raise ValueError(f"Gasto con ID {expense_id} no encontrado")

        # Delete expense
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))

        # Get updated profit
        profit = conn.execute("SELECT profit_usd FROM profit_summary").fetchone()

    return {
        "status": "ok",
        "description": expense["description"],
        "cancelled_amount": expense["amount_cents"] / 100.0,
        "profit_usd": profit["profit_usd"] if profit else 0,
    }
