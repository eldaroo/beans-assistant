"""Apply the spec 003 M2 costing tables to public and every tenant schema.

The app is multi-tenant per-schema. New tenants get the costing tables from
``database_pg.create_tenant_schema``; existing deployments need this script to
create them in each already-provisioned tenant schema. AC6: a forward loop over
``public.tenants`` creates all ten costing tables on a fresh and on an existing
seeded tenant schema, and one bad schema does not abort the loop.

Usage:
    POSTGRES_HOST=... POSTGRES_PORT=... POSTGRES_DB=... \
    POSTGRES_USER=... POSTGRES_PASSWORD=... \
    python postgres/migrations/run_03_costing_tables.py [--dry-run]

Idempotent: every statement is ``CREATE TABLE IF NOT EXISTS``, so a re-run (or a
run against a schema that already has some costing tables) is a no-op. Per-schema
failures are logged and counted but never stop the loop, so one bad tenant cannot
block migrating the rest (the schema-level analog of register_products_batch's
per-row SAVEPOINT discipline).
"""

from __future__ import annotations

import argparse
import os
import sys

# The ten costing tables, in dependency order (referenced tables first). AC6
# asserts all ten exist per schema after the migration.
COSTING_TABLE_NAMES = [
    "suppliers",
    "cost_inputs",
    "input_purchases",
    "bom_lines",
    "labor_costs",
    "packaging_costs",
    "shipping_lanes",
    "customs_duties",
    "indirect_costs",
    "landed_cost_snapshots",
]

# PostgreSQL DDL, one CREATE TABLE IF NOT EXISTS per costing table. Kept
# byte-for-byte aligned with database_pg.create_tenant_schema so a new tenant and
# a migrated existing tenant land the identical shape.
MIGRATION_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS suppliers (
        id BIGSERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        country VARCHAR(64),
        contact VARCHAR(255),
        is_active BOOLEAN DEFAULT TRUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cost_inputs (
        id BIGSERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        category VARCHAR(64),
        unit VARCHAR(32),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bom_lines (
        id BIGSERIAL PRIMARY KEY,
        product_id BIGINT NOT NULL REFERENCES products(id),
        cost_input_id BIGINT NOT NULL REFERENCES cost_inputs(id),
        country VARCHAR(64) NOT NULL,
        quantity NUMERIC(18,4) DEFAULT 1 NOT NULL CHECK (quantity > 0),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS labor_costs (
        id BIGSERIAL PRIMARY KEY,
        product_id BIGINT NOT NULL REFERENCES products(id),
        country VARCHAR(64) NOT NULL,
        batch_payment_cents INTEGER NOT NULL CHECK (batch_payment_cents >= 0),
        units_completed INTEGER NOT NULL CHECK (units_completed >= 0),
        recorded_at DATE DEFAULT CURRENT_DATE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS packaging_costs (
        id BIGSERIAL PRIMARY KEY,
        product_id BIGINT NOT NULL REFERENCES products(id),
        country VARCHAR(64) NOT NULL,
        usd_amount_cents INTEGER NOT NULL CHECK (usd_amount_cents >= 0),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS shipping_lanes (
        id BIGSERIAL PRIMARY KEY,
        product_id BIGINT NOT NULL REFERENCES products(id),
        country VARCHAR(64) NOT NULL,
        usd_amount_cents INTEGER CHECK (usd_amount_cents IS NULL OR usd_amount_cents >= 0),
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customs_duties (
        id BIGSERIAL PRIMARY KEY,
        product_id BIGINT NOT NULL REFERENCES products(id),
        country VARCHAR(64) NOT NULL,
        usd_amount_cents INTEGER CHECK (usd_amount_cents IS NULL OR usd_amount_cents >= 0),
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS indirect_costs (
        id BIGSERIAL PRIMARY KEY,
        country VARCHAR(64) NOT NULL,
        period_month VARCHAR(7) NOT NULL,
        pool_cents INTEGER NOT NULL CHECK (pool_cents >= 0),
        units_produced INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
    """,
    """
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
    )
    """,
]


def enumerate_tenant_schemas(conn) -> "list[str]":
    """Return a schema name per row in ``public.tenants`` (AC6 ground truth).

    The phone -> schema mapping is ``tenant_manager.phone_to_schema_name``. public
    itself is migrated separately (it holds no products), so only tenant schemas
    come from this loop.
    """
    from tenant_manager import phone_to_schema_name

    with conn.cursor() as cur:
        cur.execute("SELECT phone_number FROM public.tenants ORDER BY created_at")
        return [phone_to_schema_name(row[0]) for row in cur.fetchall()]


def apply_to_schema(conn, schema: str, dry_run: bool = False) -> None:
    """Create every costing table inside one tenant schema. Commits on success.

    Creates the schema first (CREATE SCHEMA IF NOT EXISTS, mirroring
    create_tenant_schema) so a public.tenants row whose schema was never
    provisioned gets a real target rather than silently falling through to public.

    A dry run EXECUTES every statement inside the transaction and then rolls the
    whole thing back, so it genuinely validates the DDL (syntax, FK-target
    existence against the real products table, dialect) without persisting. A
    print-only dry run gives false safety for a live cutover; this one can catch a
    bad statement before the real run.
    """
    from psycopg2 import sql

    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        for stmt in MIGRATION_STATEMENTS:
            cur.execute(stmt)
            if dry_run:
                print(f"  [dry-run] validated: {stmt.strip().splitlines()[0]} ...")
    if dry_run:
        conn.rollback()
    else:
        conn.commit()


def migrate_all(schemas, apply_fn):
    """Apply ``apply_fn(schema)`` to each schema, isolating per-schema failure.

    Pure control flow with no DB dependency so the "one bad schema does not abort
    the loop" guarantee (AC6) is unit-testable: a schema whose apply_fn raises is
    recorded in ``failed`` and the loop continues to the rest. Returns
    ``(ok, failed)`` where ok is the list of migrated schemas and failed is a list
    of ``(schema, error_message)`` pairs.
    """
    ok: "list[str]" = []
    failed: "list[tuple[str, str]]" = []
    for schema in schemas:
        try:
            apply_fn(schema)
            ok.append(schema)
        except Exception as exc:  # noqa: BLE001 - one bad schema must not abort the loop
            failed.append((schema, str(exc).strip()))
    return ok, failed


def main() -> int:
    import psycopg2

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        client_encoding="UTF8",
    )
    try:
        # Tenant schemas only. public holds no products table, and the costing
        # tables carry REFERENCES products(id), so applying them to public would
        # raise "relation products does not exist" and fail the run. The costing
        # model is per-tenant; public is never a target.
        schemas = enumerate_tenant_schemas(conn)
        print(f"Applying costing migration 03 to {len(schemas)} tenant schemas (dry_run={args.dry_run}).")

        def _apply(schema: str) -> None:
            print(f"-> {schema}")
            try:
                apply_to_schema(conn, schema, args.dry_run)
            except Exception:
                conn.rollback()
                raise

        ok, failed = migrate_all(schemas, _apply)
        print(f"\nResult: {len(ok)}/{len(schemas)} ok, {len(failed)} failed.")
        for schema, err in failed:
            print(f"  fail {schema}: {err}")
        return 0 if not failed else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
