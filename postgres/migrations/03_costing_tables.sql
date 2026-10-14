-- Migration 03: Beans Control Center costing tables (spec 003 M2).
--
-- Per-tenant DDL. Run inside each tenant schema's search_path. The canonical,
-- idempotent, loop-over-public.tenants applier is run_03_costing_tables.py; this
-- file is the raw DDL for a manual single-schema apply or review. Every statement
-- is CREATE TABLE IF NOT EXISTS so a re-run is a no-op.
--
--   SET search_path TO <tenant_schema>, public;
--   \i postgres/migrations/03_costing_tables.sql

-- NOTE: the suppliers.last_checkin_at column (M5, T-018) is NOT here — it is
-- added by migration 05_supplier_checkin.sql. A standalone `\i 03` then `\i 05`
-- lands the full shape; run 03 alone and the column is absent until 05 follows.
CREATE TABLE IF NOT EXISTS suppliers (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    country VARCHAR(64),
    contact VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS cost_inputs (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(64),
    unit VARCHAR(32),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS input_purchases (
    id BIGSERIAL PRIMARY KEY,
    cost_input_id BIGINT NOT NULL REFERENCES cost_inputs(id),
    supplier_id BIGINT REFERENCES suppliers(id),
    original_currency VARCHAR(3) DEFAULT 'USD' NOT NULL,
    original_amount_cents INTEGER NOT NULL CHECK (original_amount_cents >= 0),
    fx_rate NUMERIC(18,8) DEFAULT 1 NOT NULL CHECK (fx_rate > 0),
    usd_amount_cents INTEGER NOT NULL CHECK (usd_amount_cents >= 0),
    quantity NUMERIC(18,4) DEFAULT 1 NOT NULL CHECK (quantity > 0),
    purchased_at DATE DEFAULT CURRENT_DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS bom_lines (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    cost_input_id BIGINT NOT NULL REFERENCES cost_inputs(id),
    country VARCHAR(64) NOT NULL,
    quantity NUMERIC(18,4) DEFAULT 1 NOT NULL CHECK (quantity > 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS labor_costs (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    country VARCHAR(64) NOT NULL,
    batch_payment_cents INTEGER NOT NULL CHECK (batch_payment_cents >= 0),
    units_completed INTEGER NOT NULL CHECK (units_completed >= 0),
    recorded_at DATE DEFAULT CURRENT_DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS packaging_costs (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    country VARCHAR(64) NOT NULL,
    usd_amount_cents INTEGER NOT NULL CHECK (usd_amount_cents >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS shipping_lanes (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    country VARCHAR(64) NOT NULL,
    usd_amount_cents INTEGER CHECK (usd_amount_cents IS NULL OR usd_amount_cents >= 0),
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS customs_duties (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    country VARCHAR(64) NOT NULL,
    usd_amount_cents INTEGER CHECK (usd_amount_cents IS NULL OR usd_amount_cents >= 0),
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS indirect_costs (
    id BIGSERIAL PRIMARY KEY,
    country VARCHAR(64) NOT NULL,
    period_month VARCHAR(7) NOT NULL,
    pool_cents INTEGER NOT NULL CHECK (pool_cents >= 0),
    units_produced INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS landed_cost_snapshots (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    country VARCHAR(64) NOT NULL,
    materials_cents INTEGER,
    labor_cents INTEGER,
    packaging_cents INTEGER,
    shipping_cents INTEGER,
    customs_cents INTEGER,
    indirect_cents INTEGER,
    total_cents INTEGER NOT NULL DEFAULT 0 CHECK (total_cents >= 0),
    status VARCHAR(16) NOT NULL DEFAULT 'parcial' CHECK (status IN ('completo','parcial')),
    pending_components TEXT,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
