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
CREATE TABLE sqlite_sequence(name,seq);
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
    GROUP BY p.id, p.sku, p.name
/* stock_current(product_id,sku,name,stock_qty) */;
CREATE VIEW sales_summary AS
    SELECT
      date(COALESCE(paid_at, created_at)) AS day,
      COUNT(*) AS paid_sales_count,
      SUM(total_amount_cents) AS paid_revenue_cents
    FROM sales
    WHERE status = 'PAID'
    GROUP BY date(COALESCE(paid_at, created_at))
    ORDER BY day DESC
/* sales_summary(day,paid_sales_count,paid_revenue_cents) */;
CREATE VIEW revenue_paid AS
    SELECT
      SUM(total_amount_cents) AS total_revenue_cents,
      ROUND(SUM(total_amount_cents) / 100.0, 2) AS revenue_usd
    FROM sales
    WHERE status = 'PAID'
/* revenue_paid(total_revenue_cents,revenue_usd) */;
CREATE VIEW expenses_total AS
    SELECT
      SUM(amount_cents) AS total_expenses_cents,
      ROUND(SUM(amount_cents) / 100.0, 2) AS expenses_usd
    FROM expenses
/* expenses_total(total_expenses_cents,expenses_usd) */;
CREATE VIEW profit_summary AS
    SELECT
      ROUND(
        (COALESCE((SELECT revenue_usd FROM revenue_paid), 0) -
         COALESCE((SELECT expenses_usd FROM expenses_total), 0)),
        2
      ) AS profit_usd
/* profit_summary(profit_usd) */;
