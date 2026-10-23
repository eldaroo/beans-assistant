-- Analytics views ported verbatim from the per-tenant schema (database_pg.py).
-- Applied after the Drizzle table migration. Drizzle does not manage views, so
-- this file is applied directly (apply script in M1; idempotent CREATE OR REPLACE).

CREATE OR REPLACE VIEW revenue_paid AS
SELECT COALESCE(SUM(total_amount_cents), 0) AS total_revenue_cents
FROM sales WHERE status = 'PAID';

CREATE OR REPLACE VIEW expenses_total AS
SELECT COALESCE(SUM(
    CASE WHEN category = 'CANCELACION' THEN -amount_cents ELSE amount_cents END
), 0) AS total_expenses_cents
FROM expenses;

CREATE OR REPLACE VIEW profit_summary AS
SELECT (r.total_revenue_cents - e.total_expenses_cents) / 100.0 AS profit_usd
FROM revenue_paid r, expenses_total e;

CREATE OR REPLACE VIEW stock_current AS
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
WHERE p.is_active = TRUE
GROUP BY p.id, p.sku, p.name;

CREATE OR REPLACE VIEW sales_summary AS
SELECT
  DATE(created_at) AS day,
  COUNT(*) FILTER (WHERE status = 'PAID') AS paid_sales_count,
  COALESCE(SUM(total_amount_cents) FILTER (WHERE status = 'PAID'), 0) AS paid_revenue_cents
FROM sales
GROUP BY DATE(created_at);
