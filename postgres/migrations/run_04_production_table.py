"""Apply the spec 003 M3 production table to every tenant schema.

The app is multi-tenant per-schema. New tenants get ``production_records`` from
``database_pg.create_tenant_schema``; existing deployments need this script to
create it in each already-provisioned tenant schema. A forward loop over
``public.tenants`` creates the table on a fresh and on an existing seeded tenant
schema, and one bad schema does not abort the loop (the same discipline as
run_03_costing_tables.py).

Usage:
    POSTGRES_HOST=... POSTGRES_PORT=... POSTGRES_DB=... \
    POSTGRES_USER=... POSTGRES_PASSWORD=... \
    python postgres/migrations/run_04_production_table.py [--dry-run]

Idempotent: the statement is ``CREATE TABLE IF NOT EXISTS``, so a re-run (or a
run against a schema that already has the table) is a no-op. Per-schema failures
are logged and counted but never stop the loop, so one bad tenant cannot block
migrating the rest.
"""

from __future__ import annotations

import argparse
import os
import sys

# The M3 production table. A separate migration from run_03's ten costing tables:
# run_03 already shipped (M2), so M3 appends its table in its own forward loop
# rather than editing an applied migration.
PRODUCTION_TABLE_NAMES = [
    "production_records",
]

# PostgreSQL DDL, kept byte-for-byte aligned with
# database_pg.create_tenant_schema so a new tenant and a migrated existing tenant
# land the identical shape.
MIGRATION_STATEMENTS = [
    """
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
    )
    """,
]


def enumerate_tenant_schemas(conn) -> "list[str]":
    """Return a schema name per row in ``public.tenants``.

    The phone -> schema mapping is ``tenant_manager.phone_to_schema_name``. public
    itself is never a target: production_records carries REFERENCES products(id)
    and public holds no products table, so applying it to public would raise.
    """
    from tenant_manager import phone_to_schema_name

    with conn.cursor() as cur:
        cur.execute("SELECT phone_number FROM public.tenants ORDER BY created_at")
        return [phone_to_schema_name(row[0]) for row in cur.fetchall()]


def apply_to_schema(conn, schema: str, dry_run: bool = False) -> None:
    """Create the production table inside one tenant schema. Commits on success.

    Creates the schema first (CREATE SCHEMA IF NOT EXISTS, mirroring
    create_tenant_schema) so a public.tenants row whose schema was never
    provisioned gets a real target rather than silently falling through to public.

    A dry run EXECUTES the statement inside the transaction and then rolls the
    whole thing back, so it genuinely validates the DDL (syntax, FK-target
    existence against the real products table, dialect) without persisting.
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
    the loop" guarantee is unit-testable: a schema whose apply_fn raises is
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
        schemas = enumerate_tenant_schemas(conn)
        print(f"Applying production migration 04 to {len(schemas)} tenant schemas (dry_run={args.dry_run}).")

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
