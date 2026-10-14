"""Add the spec 003 M5 supplier check-in column to every tenant schema.

The app is multi-tenant per-schema. New tenants get ``suppliers.last_checkin_at``
from ``database_pg.create_tenant_schema``; existing deployments need this script
to add the column to each already-provisioned tenant schema. A forward loop over
``public.tenants`` adds the column on a fresh and on an existing seeded tenant
schema, and one bad schema does not abort the loop (the same discipline as
run_04_production_table.py).

``last_checkin_at`` stores the last recorded check-in/reply from a supplier
(T-018/AC13). The overdue-check-in attention signal reads it from stored data;
no message is sent. The messaging ledger and the actual send path stay behind
their named-human gate in M7.

Usage:
    POSTGRES_HOST=... POSTGRES_PORT=... POSTGRES_DB=... \
    POSTGRES_USER=... POSTGRES_PASSWORD=... \
    python postgres/migrations/run_05_supplier_checkin.py [--dry-run]

Idempotent: the statement is ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``, so a
re-run (or a run against a schema that already has the column) is a no-op.
Per-schema failures are logged and counted but never stop the loop.
"""

from __future__ import annotations

import argparse
import os
import sys

# PostgreSQL DDL, kept aligned with the suppliers table in
# database_pg.create_tenant_schema (the column lands the identical shape).
MIGRATION_STATEMENTS = [
    "ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS last_checkin_at TIMESTAMP",
]


def enumerate_tenant_schemas(conn) -> "list[str]":
    """Return a schema name per row in ``public.tenants`` (phone -> schema via
    ``tenant_manager.phone_to_schema_name``). public itself is never a target."""
    from tenant_manager import phone_to_schema_name

    with conn.cursor() as cur:
        cur.execute("SELECT phone_number FROM public.tenants ORDER BY created_at")
        return [phone_to_schema_name(row[0]) for row in cur.fetchall()]


def apply_to_schema(conn, schema: str, dry_run: bool = False) -> None:
    """Add the check-in column inside one tenant schema. Commits on success.

    A dry run EXECUTES the statement inside the transaction and then rolls the
    whole thing back, so it genuinely validates the DDL (the suppliers table must
    exist in the schema) without persisting. The ALTER targets the schema's own
    suppliers table via search_path."""
    from psycopg2 import sql

    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        for stmt in MIGRATION_STATEMENTS:
            cur.execute(stmt)
            if dry_run:
                print(f"  [dry-run] validated: {stmt}")
    if dry_run:
        conn.rollback()
    else:
        conn.commit()


def migrate_all(schemas, apply_fn):
    """Apply ``apply_fn(schema)`` to each schema, isolating per-schema failure.

    Pure control flow with no DB dependency so the "one bad schema does not abort
    the loop" guarantee is unit-testable. Returns ``(ok, failed)``."""
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
        print(f"Applying supplier check-in migration 05 to {len(schemas)} tenant schemas (dry_run={args.dry_run}).")

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
