-- Migration 04: Beans Control Center production table (spec 003 M3).
--
-- Per-tenant DDL. Run inside each tenant schema's search_path. The canonical,
-- idempotent, loop-over-public.tenants applier is run_04_production_table.py;
-- this file is the raw DDL for a manual single-schema apply or review. Every
-- statement is CREATE TABLE IF NOT EXISTS so a re-run is a no-op.
--
--   SET search_path TO <tenant_schema>, public;
--   \i postgres/migrations/04_production_table.sql

CREATE TABLE IF NOT EXISTS production_records (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT REFERENCES products(id),
    country VARCHAR(64) NOT NULL,
    period_week VARCHAR(8) NOT NULL,
    units_produced INTEGER NOT NULL DEFAULT 0 CHECK (units_produced >= 0),
    units_target INTEGER CHECK (units_target IS NULL OR units_target >= 0),
    expected_next_at DATE,
    recorded_at DATE DEFAULT CURRENT_DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
