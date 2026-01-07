-- PostgreSQL Schema for Beans&Co Multi-Tenant System
-- Auto-executed on first container startup

-- Enable UUID extension (useful for future features)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =========================
-- PRODUCTS TABLE
-- =========================
CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    sku VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    unit_cost_cents INTEGER NOT NULL DEFAULT 0,
    unit_price_cents INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CONSTRAINT check_unit_cost_positive CHECK (unit_cost_cents >= 0),
    CONSTRAINT check_unit_price_positive CHECK (unit_price_cents >= 0)
);

CREATE INDEX idx_products_sku ON products(sku);
CREATE INDEX idx_products_is_active ON products(is_active);
CREATE INDEX idx_products_created_at ON products(created_at);

-- =========================
-- SALES TABLE
-- =========================
CREATE TABLE IF NOT EXISTS sales (
    id BIGSERIAL PRIMARY KEY,
    sale_number VARCHAR(50) NOT NULL UNIQUE,
    customer_name VARCHAR(255),
    status VARCHAR(20) NOT NULL CHECK (status IN ('PAID','PENDING','CANCELLED')),
    currency VARCHAR(3) DEFAULT 'USD' NOT NULL,
    total_amount_cents INTEGER NOT NULL CHECK (total_amount_cents >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    paid_at TIMESTAMP
);

CREATE INDEX idx_sales_sale_number ON sales(sale_number);
CREATE INDEX idx_sales_status ON sales(status);
CREATE INDEX idx_sales_created_at ON sales(created_at);

-- =========================
-- SALE ITEMS TABLE
-- =========================
CREATE TABLE IF NOT EXISTS sale_items (
    id BIGSERIAL PRIMARY KEY,
    sale_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL,
    line_total_cents INTEGER NOT NULL,

    CONSTRAINT fk_sale_items_sale FOREIGN KEY(sale_id) REFERENCES sales(id) ON DELETE CASCADE,
    CONSTRAINT fk_sale_items_product FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE INDEX idx_sale_items_sale_id ON sale_items(sale_id);
CREATE INDEX idx_sale_items_product_id ON sale_items(product_id);

-- =========================
-- STOCK MOVEMENTS TABLE
-- =========================
CREATE TABLE IF NOT EXISTS stock_movements (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL,
    movement_type VARCHAR(20) NOT NULL CHECK (movement_type IN ('IN','OUT','ADJUSTMENT')),
    quantity INTEGER NOT NULL CHECK (quantity <> 0),
    reason TEXT,
    reference VARCHAR(100),
    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,

    CONSTRAINT fk_stock_movements_product FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE INDEX idx_stock_movements_product_id ON stock_movements(product_id);
CREATE INDEX idx_stock_movements_type ON stock_movements(movement_type);
CREATE INDEX idx_stock_movements_occurred_at ON stock_movements(occurred_at);

-- =========================
-- EXPENSES TABLE
-- =========================
CREATE TABLE IF NOT EXISTS expenses (
    id BIGSERIAL PRIMARY KEY,
    expense_date DATE DEFAULT CURRENT_DATE NOT NULL,
    category VARCHAR(50) NOT NULL,
    description TEXT,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    currency VARCHAR(3) DEFAULT 'USD' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX idx_expenses_expense_date ON expenses(expense_date);
CREATE INDEX idx_expenses_category ON expenses(category);
CREATE INDEX idx_expenses_created_at ON expenses(created_at);

-- =========================
-- VIEWS
-- =========================

-- Revenue from paid sales
CREATE OR REPLACE VIEW revenue_paid AS
SELECT COALESCE(SUM(total_amount_cents), 0) AS total_revenue_cents
FROM sales WHERE status = 'PAID';

-- Total expenses
CREATE OR REPLACE VIEW expenses_total AS
SELECT COALESCE(SUM(amount_cents), 0) AS total_expenses_cents
FROM expenses;

-- Profit summary
CREATE OR REPLACE VIEW profit_summary AS
SELECT (r.total_revenue_cents - e.total_expenses_cents) / 100.0 AS profit_usd
FROM revenue_paid r, expenses_total e;

-- Current stock for all active products
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

-- =========================
-- TENANT MANAGEMENT (For multi-tenant support)
-- =========================

-- Schema per tenant approach: Each tenant gets their own schema
-- Function to create a new tenant schema
CREATE OR REPLACE FUNCTION create_tenant_schema(tenant_name VARCHAR)
RETURNS VOID AS $$
BEGIN
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', tenant_name);

    -- Set search_path to new schema
    EXECUTE format('SET search_path TO %I', tenant_name);

    -- Create all tables in the tenant schema
    -- (Schema creation script would be executed in context of that schema)
END;
$$ LANGUAGE plpgsql;

-- Initial setup complete
DO $$
BEGIN
    RAISE NOTICE 'Beans&Co PostgreSQL schema initialized successfully!';
END $$;
