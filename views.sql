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
  product_id,
  SUM(
    CASE
      WHEN movement_type IN ('IN', 'ADJUSTMENT') THEN quantity
      WHEN movement_type = 'OUT' THEN -quantity
    END
  ) AS stock_qty
FROM stock_movements
GROUP BY product_id;
