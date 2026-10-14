-- Complete Database Initialization for Beans&Co
-- Run with: sqlite3 beansco.db < init_complete_database.sql

-- Drop everything first (clean slate). Children before parents so the order is
-- safe even if FK enforcement is ever enabled.
DROP TABLE IF EXISTS production_records;
DROP TABLE IF EXISTS landed_cost_snapshots;
DROP TABLE IF EXISTS indirect_costs;
DROP TABLE IF EXISTS customs_duties;
DROP TABLE IF EXISTS shipping_lanes;
DROP TABLE IF EXISTS packaging_costs;
DROP TABLE IF EXISTS labor_costs;
DROP TABLE IF EXISTS bom_lines;
DROP TABLE IF EXISTS input_purchases;
DROP TABLE IF EXISTS cost_inputs;
DROP TABLE IF EXISTS suppliers;
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
-- Costing tables (spec 003 M2), dropped before their referenced tables are recreated.
DROP TABLE IF EXISTS production_records;
DROP TABLE IF EXISTS landed_cost_snapshots;
DROP TABLE IF EXISTS indirect_costs;
DROP TABLE IF EXISTS customs_duties;
DROP TABLE IF EXISTS shipping_lanes;
DROP TABLE IF EXISTS packaging_costs;
DROP TABLE IF EXISTS labor_costs;
DROP TABLE IF EXISTS bom_lines;
DROP TABLE IF EXISTS input_purchases;
DROP TABLE IF EXISTS cost_inputs;
DROP TABLE IF EXISTS suppliers;

-- Create Tables
CREATE TABLE products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sku TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  unit_cost_cents INTEGER NOT NULL CHECK (unit_cost_cents >= 0),
  unit_price_cents INTEGER CHECK (unit_price_cents IS NULL OR unit_price_cents >= 0),
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
    WHERE p.is_active = 1  -- Only show active products
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

-- Insert Initial Stock (skip products with 0 stock)
INSERT INTO stock_movements (product_id, movement_type, quantity, reason) VALUES
(1, 'IN', 3, 'Stock inicial'),
(2, 'IN', 97, 'Stock inicial'),
(3, 'IN', 3, 'Stock inicial');
-- Product 4 (Llavero) starts with 0 stock, no movement needed

-- ============================================================================
-- Costing tables (spec 003 M2 — Beans Control Center costing module)
-- The ten costing tables keyed by product_id and/or country. Money is in
-- integer *_cents columns. A nullable *_cents column means the component is
-- pending (unknown yet), never a real zero — the completeness state reads it.
-- ============================================================================
CREATE TABLE suppliers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  country TEXT,
  contact TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE cost_inputs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category TEXT,
  unit TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Multi-currency, append-only (AC7). A correction is a new row; the original
-- is never mutated. original_* is what was paid; usd_amount_cents is derived
-- from fx_rate at purchase time and stored, so a wrong rate stays visible.
CREATE TABLE input_purchases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cost_input_id INTEGER NOT NULL,
  supplier_id INTEGER,
  original_currency TEXT NOT NULL DEFAULT 'USD',
  original_amount_cents INTEGER NOT NULL CHECK (original_amount_cents >= 0),
  fx_rate REAL NOT NULL DEFAULT 1.0 CHECK (fx_rate > 0),
  usd_amount_cents INTEGER NOT NULL CHECK (usd_amount_cents >= 0),
  quantity REAL NOT NULL DEFAULT 1 CHECK (quantity > 0),
  purchased_at TEXT NOT NULL DEFAULT (date('now')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (cost_input_id) REFERENCES cost_inputs(id),
  FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

-- The recipe: which inputs and how many go into one bracelet, per country.
CREATE TABLE bom_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL,
  cost_input_id INTEGER NOT NULL,
  country TEXT NOT NULL,
  quantity REAL NOT NULL DEFAULT 1 CHECK (quantity > 0),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (product_id) REFERENCES products(id),
  FOREIGN KEY (cost_input_id) REFERENCES cost_inputs(id)
);

-- Direct labor as a batch payment over units completed (AC11 completed basis).
CREATE TABLE labor_costs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL,
  country TEXT NOT NULL,
  batch_payment_cents INTEGER NOT NULL CHECK (batch_payment_cents >= 0),
  units_completed INTEGER NOT NULL CHECK (units_completed >= 0),
  recorded_at TEXT NOT NULL DEFAULT (date('now')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE packaging_costs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL,
  country TEXT NOT NULL,
  usd_amount_cents INTEGER NOT NULL CHECK (usd_amount_cents >= 0),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (product_id) REFERENCES products(id)
);

-- usd_amount_cents nullable: a lane with no quoted price is pending, not zero.
CREATE TABLE shipping_lanes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL,
  country TEXT NOT NULL,
  usd_amount_cents INTEGER CHECK (usd_amount_cents IS NULL OR usd_amount_cents >= 0),
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (product_id) REFERENCES products(id)
);

-- usd_amount_cents nullable: a duty not yet known is pending, not zero.
CREATE TABLE customs_duties (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL,
  country TEXT NOT NULL,
  usd_amount_cents INTEGER CHECK (usd_amount_cents IS NULL OR usd_amount_cents >= 0),
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (product_id) REFERENCES products(id)
);

-- Indirect pool per country per calendar month. units_produced NULL or 0 means
-- indirect allocation is PENDING for that month (never a divide by zero, AC12).
CREATE TABLE indirect_costs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  country TEXT NOT NULL,
  period_month TEXT NOT NULL,
  pool_cents INTEGER NOT NULL CHECK (pool_cents >= 0),
  units_produced INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- The derived landed-cost snapshot (D-016/D-022). A *_cents component column is
-- NULL when that component is pending. status is 'completo' only when all six
-- components are filled; otherwise 'parcial' and pending_components names them.
CREATE TABLE landed_cost_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL,
  country TEXT NOT NULL,
  materials_cents INTEGER,
  labor_cents INTEGER,
  packaging_cents INTEGER,
  shipping_cents INTEGER,
  customs_cents INTEGER,
  indirect_cents INTEGER,
  total_cents INTEGER NOT NULL DEFAULT 0 CHECK (total_cents >= 0),
  status TEXT NOT NULL DEFAULT 'parcial' CHECK (status IN ('completo','parcial')),
  pending_components TEXT,
  computed_at TEXT NOT NULL DEFAULT (datetime('now')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (product_id) REFERENCES products(id)
);

-- Production module (spec 003 M3). Units produced per week against a target, per
-- country. expected_next_at is the date the next batch is expected; an overdue
-- one drives an arrival-cadence attention item (T-011). units_target NULL means
-- no meta set for that week (never read as a zero target). The monthly sum of
-- units_produced per country is the indirect-allocation denominator M4 wires in.
CREATE TABLE production_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER,
  country TEXT NOT NULL,
  period_week TEXT NOT NULL,
  units_produced INTEGER NOT NULL DEFAULT 0 CHECK (units_produced >= 0),
  units_target INTEGER CHECK (units_target IS NULL OR units_target >= 0),
  expected_next_at TEXT,
  recorded_at TEXT NOT NULL DEFAULT (date('now')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (product_id) REFERENCES products(id)
);
