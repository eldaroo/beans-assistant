"""Production migration tests (spec 003 M3).

The M3 production table (``production_records``) is a separate forward migration
from run_03's ten costing tables: run_03 already shipped in M2, so M3 appends its
table in run_04 rather than editing an applied migration. These verify (against
SQLite, the repo's DB-test backend):
  - the production table exists on a freshly provisioned schema (new tenant);
  - an existing seeded schema gains the table when the runtime DDL is re-applied,
    idempotently (CREATE TABLE IF NOT EXISTS), data untouched;
  - run_04's forward-loop control flow isolates a failing schema and continues,
    and targets tenant schemas only (public is never a target);
  - run_04's Postgres statement is idempotent and creates exactly the one table.
"""
import importlib.util
import sqlite3
from pathlib import Path

import pytest

import tenant_manager


def _load_run04():
    path = Path(__file__).parent.parent.parent / "postgres" / "migrations" / "run_04_production_table.py"
    spec = importlib.util.spec_from_file_location("run_04_production_table", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tables_in(conn) -> set:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


# --------------------------------------------------------------- AC fresh

@pytest.mark.unit
@pytest.mark.database
def test_fresh_tenant_schema_has_production_table(test_db):
    import database

    with database.get_conn() as conn:
        assert "production_records" in _tables_in(conn)


# ----------------------------------------------- existing-schema idempotency

@pytest.mark.unit
@pytest.mark.database
def test_existing_seeded_schema_gains_production_table_without_disturbing_data():
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(
            "CREATE TABLE products ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  sku TEXT NOT NULL UNIQUE,"
            "  name TEXT NOT NULL,"
            "  is_active INTEGER NOT NULL DEFAULT 1"
            ");"
        )
        conn.execute("INSERT INTO products (sku, name) VALUES ('BC-X', 'Pulsera X')")
        conn.commit()
        assert "production_records" not in _tables_in(conn), "precondition: no production table yet"

        conn.executescript(tenant_manager.TenantManager._get_default_schema(None))

        assert "production_records" in _tables_in(conn), "existing schema gains the production table"
        rows = conn.execute("SELECT sku FROM products").fetchall()
        assert [r[0] for r in rows] == ["BC-X"], "existing product data must be untouched"
    finally:
        conn.close()


@pytest.mark.unit
@pytest.mark.database
def test_runtime_schema_is_idempotent_for_production():
    schema_sql = tenant_manager.TenantManager._get_default_schema(None)
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(schema_sql)  # fresh
        conn.executescript(schema_sql)  # re-apply must not raise
        assert "production_records" in _tables_in(conn)
    finally:
        conn.close()


# ------------------------------------------- one bad schema does not abort

@pytest.mark.unit
def test_migrate_all_isolates_a_bad_schema_and_continues():
    run04 = _load_run04()
    applied = []

    def apply_fn(schema):
        if schema == "tenant_bad":
            raise RuntimeError("boom in this schema")
        applied.append(schema)

    ok, failed = run04.migrate_all(["tenant_a", "tenant_bad", "tenant_c"], apply_fn)

    assert ok == ["tenant_a", "tenant_c"]
    assert applied == ["tenant_a", "tenant_c"]
    assert len(failed) == 1 and failed[0][0] == "tenant_bad"
    assert "boom" in failed[0][1]


# --------------------------------------------- statements shape and coverage

class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        pass

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)


@pytest.mark.unit
def test_enumerate_tenant_schemas_is_tenant_only_never_public():
    run04 = _load_run04()
    conn = _FakeConn([("+5491153695627",), ("+14155550000",)])

    schemas = run04.enumerate_tenant_schemas(conn)

    assert "public" not in schemas, "public must never be a migration target"
    assert len(schemas) == 2
    assert all(s.startswith("tenant_") for s in schemas), schemas


@pytest.mark.unit
def test_migration_statement_is_idempotent_and_covers_the_table():
    run04 = _load_run04()

    assert run04.PRODUCTION_TABLE_NAMES == ["production_records"]
    assert len(run04.MIGRATION_STATEMENTS) == 1
    stmt = run04.MIGRATION_STATEMENTS[0]
    assert "CREATE TABLE IF NOT EXISTS production_records" in stmt
