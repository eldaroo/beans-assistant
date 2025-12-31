-- Complete Database Initialization for Beans&Co
-- Run with: sqlite3 beansco.db < init_complete_database.sql

-- Drop everything first (clean slate)
DROP TABLE IF EXISTS stock_movements;
DROP TABLE IF EXISTS sale_items;
DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS expenses;
DROP TABLE IF EXISTS products;
DROP VIEW IF EXISTS stock_current;
DROP VIEW IF EXISTS sales_summary;
DROP VIEW IF EXISTS revenue_paid;
DROP VIEW IF EXISTS expenses_total;
DROP VIEW IF EXISTS profit_summary;

-- Create Tables
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
  movement_type TEXT NOT NULL CHECK (movement_type IN ('IN','OUT','ADJUSTMENT')),
  quantity INTEGER NOT NULL CHECK (quantity <> 0),
  reason TEXT,
  reference TEXT,
  occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE sales (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sale_number TEXT NOT NULL UNIQUE,
  customer_name TEXT,
  status TEXT NOT NULL CHECK (status IN ('PAID','PENDING','CANCELLED')),
  currency TEXT NOT NULL DEFAULT 'USD',
  total_amount_cents INTEGER NOT NULL CHECK (total_amount_cents >= 0),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  paid_at TEXT
);

CREATE TABLE sale_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sale_id INTEGER NOT NULL,
  product_id INTEGER NOT NULL,
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
  line_total_cents INTEGER NOT NULL CHECK (line_total_cents >= 0),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (sale_id) REFERENCES sales(id),
  FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  expense_date TEXT NOT NULL DEFAULT (date('now')),
  category TEXT NOT NULL,
  description TEXT,
  amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
  currency TEXT NOT NULL DEFAULT 'USD',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Create Views
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

CREATE VIEW sales_summary AS
    SELECT
      date(COALESCE(paid_at, created_at)) AS day,
      COUNT(*) AS paid_sales_count,
      SUM(total_amount_cents) AS paid_revenue_cents
    FROM sales
    WHERE status = 'PAID'
    GROUP BY date(COALESCE(paid_at, created_at))
    ORDER BY day DESC;

CREATE VIEW revenue_paid AS
    SELECT
      SUM(total_amount_cents) AS total_revenue_cents,
      ROUND(SUM(total_amount_cents) / 100.0, 2) AS revenue_usd
    FROM sales
    WHERE status = 'PAID';

CREATE VIEW expenses_total AS
    SELECT
      SUM(amount_cents) AS total_expenses_cents,
      ROUND(SUM(amount_cents) / 100.0, 2) AS expenses_usd
    FROM expenses;

CREATE VIEW profit_summary AS
    SELECT
      ROUND(
        (COALESCE((SELECT revenue_usd FROM revenue_paid), 0) -
         COALESCE((SELECT expenses_usd FROM expenses_total), 0)),
        2
      ) AS profit_usd;

-- Insert Default Products
INSERT INTO products (sku, name, description, unit_price_cents, unit_cost_cents) VALUES
('BC-BRACELET-CLASSIC', 'Pulsera de Granos de Café - Clásica', 'Pulsera artesanal hecha con granos de café', 1200, 400),
('BC-BRACELET-BLACK', 'Pulsera de Granos de Café - Negra', 'Pulsera artesanal de granos de café negros', 1400, 450),
('BC-BRACELET-GOLD', 'Pulsera de Granos de Café - Dorada', 'Pulsera artesanal de granos de café dorados', 1600, 500),
('BC-KEYCHAIN', 'Llavero de Granos de Café', 'Llavero artesanal hecho con granos de café', 800, 250);

-- Insert Initial Stock
INSERT INTO stock_movements (product_id, movement_type, quantity, reason) VALUES
(1, 'IN', 3, 'Stock inicial'),
(2, 'IN', 97, 'Stock inicial'),
(3, 'IN', 3, 'Stock inicial'),
(4, 'IN', 0, 'Stock inicial');
