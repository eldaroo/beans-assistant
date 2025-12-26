PRAGMA foreign_keys = ON;

-- Drop (para reiniciar fácil)
DROP TABLE IF EXISTS sale_items;
DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS stock_movements;
DROP TABLE IF EXISTS expenses;
DROP TABLE IF EXISTS products;

-- PRODUCTS
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

-- STOCK MOVEMENTS
-- movement_type: IN | OUT | ADJUSTMENT
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

-- SALES
-- status: PAID | PENDING | CANCELLED
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

-- SALE ITEMS
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

-- EXPENSES
CREATE TABLE expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  expense_date TEXT NOT NULL DEFAULT (date('now')),
  category TEXT NOT NULL,
  description TEXT,
  amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
  currency TEXT NOT NULL DEFAULT 'USD',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- VIEWS

-- Current stock per product from movements
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

-- Daily paid sales summary
CREATE VIEW sales_summary AS
SELECT
  date(COALESCE(paid_at, created_at)) AS day,
  COUNT(*) AS paid_sales_count,
  SUM(total_amount_cents) AS paid_revenue_cents
FROM sales
WHERE status = 'PAID'
GROUP BY date(COALESCE(paid_at, created_at))
ORDER BY day DESC;

-- DUMMY DATA

INSERT INTO products (sku, name, description, unit_cost_cents, unit_price_cents) VALUES
('BC-BRACELET-CLASSIC', 'Coffee Bean Bracelet - Classic', 'Handmade bracelet with coffee beans', 350, 1200),
('BC-BRACELET-BLACK',   'Coffee Bean Bracelet - Black',   'Black cord, coffee beans',           400, 1400),
('BC-BRACELET-GOLD',    'Coffee Bean Bracelet - Gold',    'Gold accents + coffee beans',        550, 2000),
('BC-KEYCHAIN',         'Coffee Bean Keychain',           'Keychain made with coffee beans',    200, 800);

-- Stock IN
INSERT INTO stock_movements (product_id, movement_type, quantity, reason, reference, occurred_at) VALUES
(1, 'IN',  50, 'Initial stock', 'INIT-001', datetime('now','-20 days')),
(2, 'IN',  40, 'Initial stock', 'INIT-001', datetime('now','-20 days')),
(3, 'IN',  25, 'Initial stock', 'INIT-001', datetime('now','-20 days')),
(4, 'IN',  60, 'Initial stock', 'INIT-001', datetime('now','-20 days'));

-- Expenses
INSERT INTO expenses (expense_date, category, description, amount_cents, currency) VALUES
(date('now','-18 days'), 'Materials', 'Coffee beans batch A', 12000, 'USD'),
(date('now','-17 days'), 'Packaging', 'Boxes and labels', 4500, 'USD'),
(date('now','-10 days'), 'Marketing', 'Instagram ads', 8000, 'USD'),
(date('now','-5 days'),  'Shipping',  'Courier account top-up', 3000, 'USD');

-- Sales + items + stock OUT
INSERT INTO sales (sale_number, customer_name, status, currency, total_amount_cents, created_at, paid_at) VALUES
('S-1001', 'Ana',   'PAID',     'USD', 2600, datetime('now','-12 days'), datetime('now','-12 days')),
('S-1002', 'Luis',  'PAID',     'USD', 1400, datetime('now','-8 days'),  datetime('now','-8 days')),
('S-1003', 'Mia',   'PENDING',  'USD', 2000, datetime('now','-3 days'),  NULL),
('S-1004', 'Joao',  'CANCELLED','USD', 1200, datetime('now','-2 days'),  NULL),
('S-1005', 'Sofi',  'PAID',     'USD', 3200, datetime('now','-1 days'),  datetime('now','-1 days'));

-- Items for S-1001 (2 classic + 1 keychain)
INSERT INTO sale_items (sale_id, product_id, quantity, unit_price_cents, line_total_cents) VALUES
(1, 1, 2, 1200, 2400),
(1, 4, 1,  800,  800);

-- Items for S-1002 (1 black)
INSERT INTO sale_items (sale_id, product_id, quantity, unit_price_cents, line_total_cents) VALUES
(2, 2, 1, 1400, 1400);

-- Items for S-1003 pending (1 gold)
INSERT INTO sale_items (sale_id, product_id, quantity, unit_price_cents, line_total_cents) VALUES
(3, 3, 1, 2000, 2000);

-- Items for S-1004 cancelled (1 classic)
INSERT INTO sale_items (sale_id, product_id, quantity, unit_price_cents, line_total_cents) VALUES
(4, 1, 1, 1200, 1200);

-- Items for S-1005 paid (2 black + 1 classic)
INSERT INTO sale_items (sale_id, product_id, quantity, unit_price_cents, line_total_cents) VALUES
(5, 2, 2, 1400, 2800),
(5, 1, 1, 1200, 1200);

-- Stock OUT should reflect PAID sales only (we record OUT only for PAID sales)
INSERT INTO stock_movements (product_id, movement_type, quantity, reason, reference, occurred_at) VALUES
(1, 'OUT', 2, 'Sale S-1001', 'S-1001', datetime('now','-12 days')),
(4, 'OUT', 1, 'Sale S-1001', 'S-1001', datetime('now','-12 days')),
(2, 'OUT', 1, 'Sale S-1002', 'S-1002', datetime('now','-8 days')),
(2, 'OUT', 2, 'Sale S-1005', 'S-1005', datetime('now','-1 days')),
(1, 'OUT', 1, 'Sale S-1005', 'S-1005', datetime('now','-1 days'));
