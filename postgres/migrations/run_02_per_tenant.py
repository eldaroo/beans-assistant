"""Apply migration 02_allow_product_price_null to public schema and every tenant schema.

The app is multi-tenant per-schema. Each tenant has its own schema with its own
products table. Postgres init scripts (postgres/init/*.sql) only run on a fresh
data directory; existing deployments need this script to relax the
unit_price_cents NOT NULL constraint everywhere it lives.

Usage:
    POSTGRES_HOST=... POSTGRES_PORT=... POSTGRES_DB=... \
    POSTGRES_USER=... POSTGRES_PASSWORD=... \
    python postgres/migrations/run_02_per_tenant.py [--dry-run]

Idempotent: ALTER ... DROP NOT NULL is a no-op on a column that is already
nullable, and DROP CONSTRAINT IF EXISTS handles re-runs of the CHECK swap.
Per-schema failures are logged and counted but do not stop the loop, so a
single bad tenant cannot block migrating the rest.
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg2
from psycopg2 import sql


MIGRATION_STATEMENTS = [
    "ALTER TABLE products ALTER COLUMN unit_price_cents DROP NOT NULL",
    "ALTER TABLE products DROP CONSTRAINT IF EXISTS check_unit_price_positive",
    "ALTER TABLE products ADD CONSTRAINT check_unit_price_positive "
    "CHECK (unit_price_cents IS NULL OR unit_price_cents >= 0)",
]


def list_schemas_with_products(conn) -> list[str]:
    """Return every schema (including public) that owns a products table.

    The mapping tenant phone → schema lives in tenant_manager.phone_to_schema_name,
    but the live schemas are the ground truth: any schema that owns a products
    table needs the migration. public typically does not in this deployment;
    excluding by absence keeps the script idempotent across environments.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT n.nspname
            FROM pg_namespace n
            JOIN pg_class c ON c.relnamespace = n.oid
            WHERE c.relname = 'products'
              AND c.relkind = 'r'
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
              AND n.nspname NOT LIKE 'pg_%'
            ORDER BY n.nspname
            """
        )
        return [row[0] for row in cur.fetchall()]


def apply_migration(conn, schema: str, dry_run: bool) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema))
        )
        for stmt in MIGRATION_STATEMENTS:
            if dry_run:
                print(f"  [dry-run] {stmt}")
            else:
                cur.execute(stmt)
        if not dry_run:
            conn.commit()


def main() -> int:
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
        schemas = list_schemas_with_products(conn)
        print(f"Applying migration 02 to {len(schemas)} schemas (dry_run={args.dry_run}).")

        ok = 0
        failed: list[tuple[str, str]] = []
        for schema in schemas:
            print(f"-> {schema}")
            try:
                apply_migration(conn, schema, args.dry_run)
                ok += 1
            except psycopg2.Error as exc:
                conn.rollback()
                failed.append((schema, str(exc).strip()))
                print(f"   FAILED: {exc}")

        print(f"\nResult: {ok}/{len(schemas)} ok, {len(failed)} failed.")
        for schema, err in failed:
            print(f"  fail {schema}: {err}")

        return 0 if not failed else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
