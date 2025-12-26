import sqlite3
import pytest
import time

import database
from database import (
    register_product,
    add_stock,
    register_sale,
    fetch_one,
)

# =========================
# TEST DB FIXTURE (AISLADA)
# =========================

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_beansco.db"

    # Forzar a database.py a usar esta DB
    monkeypatch.setattr(database, "DB_PATH", str(db_file))

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    # =========================
    # SCHEMA REAL (alineado a prod)
    # =========================
    cur.executescript("""
    CREATE TABLE products (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      sku TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      description TEXT,
      unit_cost_cents INTEGER NOT NULL CHECK (unit_cost_cents >= 0),
      unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
      is_active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE stock_movements (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_id INTEGER NOT NULL,
      movement_type TEXT NOT NULL,
      quantity INTEGER NOT NULL,
      reason TEXT,
      created_at TEXT
    );

    CREATE TABLE sales (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      sale_number TEXT NOT NULL,
      total_amount_cents INTEGER NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE sale_items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      sale_id INTEGER NOT NULL,
      product_id INTEGER NOT NULL,
      quantity INTEGER NOT NULL,
      unit_price_cents INTEGER NOT NULL
    );

    CREATE TABLE expenses (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      amount_cents INTEGER
    );
    """)

    # =========================
    # VIEWS
    # =========================
    cur.executescript("""
    CREATE VIEW stock_current AS
    SELECT
      product_id,
      SUM(
        CASE
          WHEN movement_type IN ('IN','ADJUSTMENT') THEN quantity
          WHEN movement_type = 'OUT' THEN -quantity
        END
      ) AS stock_qty
    FROM stock_movements
    GROUP BY product_id;

    CREATE VIEW revenue_paid AS
    SELECT COALESCE(SUM(total_amount_cents), 0) AS total_revenue_cents
    FROM sales
    WHERE status = 'PAID';

    CREATE VIEW expenses_total AS
    SELECT COALESCE(SUM(amount_cents), 0) AS total_expenses_cents
    FROM expenses;

    CREATE VIEW profit_summary AS
    SELECT (r.total_revenue_cents - e.total_expenses_cents) / 100.0 AS profit_usd
    FROM revenue_paid r, expenses_total e;
    """)

    conn.commit()
    conn.close()

    yield


# =========================
# TESTS
# =========================

def test_register_product(test_db):
    res = register_product({
        "sku": "BC-BLACK",
        "name": "Black Bracelet",
        "unit_price_cents": 3500,
        "unit_cost_cents": 1200
    })

    assert res["status"] == "ok"

    row = fetch_one(
        "SELECT sku, unit_price_cents, unit_cost_cents FROM products WHERE sku = ?",
        ("BC-BLACK",)
    )

    assert row["sku"] == "BC-BLACK"
    assert row["unit_price_cents"] == 3500
    assert row["unit_cost_cents"] == 1200


def test_add_stock_increases_stock(test_db):
    register_product({
        "sku": "BC-BLACK",
        "name": "Black Bracelet",
        "unit_price_cents": 3500,
        "unit_cost_cents": 1200
    })

    add_stock({
        "product_id": 1,
        "quantity": 20,
        "reason": "Initial stock"
    })

    row = fetch_one(
        "SELECT stock_qty FROM stock_current WHERE product_id = 1"
    )

    assert row["stock_qty"] == 20


def test_register_paid_sale_decreases_stock_and_increases_revenue(test_db):
    register_product({
        "sku": "BC-BLACK",
        "name": "Black Bracelet",
        "unit_price_cents": 3500,
        "unit_cost_cents": 1200
    })

    add_stock({
        "product_id": 1,
        "quantity": 20
    })

    res = register_sale({
        "status": "PAID",
        "items": [
            {"product_id": 1, "quantity": 2}
        ]
    })

    assert res["total_usd"] == 70.0

    stock = fetch_one(
        "SELECT stock_qty FROM stock_current WHERE product_id = 1"
    )
    assert stock["stock_qty"] == 18

    revenue = fetch_one(
        "SELECT total_revenue_cents FROM revenue_paid"
    )
    assert revenue["total_revenue_cents"] == 7000


def test_pending_sale_does_not_affect_stock_or_revenue(test_db):
    register_product({
        "sku": "BC-BLACK",
        "name": "Black Bracelet",
        "unit_price_cents": 3500,
        "unit_cost_cents": 1200
    })

    add_stock({
        "product_id": 1,
        "quantity": 10
    })

    register_sale({
        "status": "PENDING",
        "items": [
            {"product_id": 1, "quantity": 3}
        ]
    })

    stock = fetch_one(
        "SELECT stock_qty FROM stock_current WHERE product_id = 1"
    )
    assert stock["stock_qty"] == 10

    revenue = fetch_one(
        "SELECT total_revenue_cents FROM revenue_paid"
    )
    assert revenue["total_revenue_cents"] == 0


def test_insufficient_stock_raises_error(test_db):
    register_product({
        "sku": "BC-BLACK",
        "name": "Black Bracelet",
        "unit_price_cents": 3500,
        "unit_cost_cents": 1200
    })

    with pytest.raises(ValueError):
        register_sale({
            "status": "PAID",
            "items": [
                {"product_id": 1, "quantity": 999}
            ]
        })
