-- =========================
-- Revenue (paid only)
-- =========================
CREATE VIEW IF NOT EXISTS revenue_paid AS
SELECT
  COALESCE(SUM(total_amount_cents), 0) AS total_revenue_cents
FROM sales
WHERE status = 'PAID';


-- =========================
-- Expenses total
-- =========================
CREATE VIEW IF NOT EXISTS expenses_total AS
SELECT
  COALESCE(SUM(amount_cents), 0) AS total_expenses_cents
FROM expenses;


-- =========================
-- Profit summary
-- =========================
CREATE VIEW IF NOT EXISTS profit_summary AS
SELECT
  (r.total_revenue_cents - e.total_expenses_cents) / 100.0 AS profit_usd
FROM revenue_paid r, expenses_total e;


-- =========================
-- Current stock per product
-- =========================
CREATE VIEW IF NOT EXISTS stock_current AS
SELECT
  p.id AS product_id,
  p.sku,
  p.name,
  COALESCE(
    SUM(
      CASE
        WHEN sm.movement_type IN ('IN', 'ADJUSTMENT') THEN sm.quantity
        WHEN sm.movement_type = 'OUT' THEN -sm.quantity
        ELSE 0
      END
    ),
    0
  ) AS stock_qty
FROM products p
LEFT JOIN stock_movements sm ON p.id = sm.product_id
WHERE p.is_active = 1
GROUP BY p.id, p.sku, p.name;
