"""Supplier check-in migration tests (spec 003 M5, T-018).

``suppliers.last_checkin_at`` is a COLUMN added to an existing table (not a new
table like M3's production_records), so fresh schemas get it from the three
create sources while existing Postgres tenants get it from run_05's idempotent
``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``. These verify (against SQLite, the
repo's DB-test backend) that the column is present on a fresh schema and that
run_05's forward-loop control flow isolates a failing schema and targets tenant
schemas only.
"""
import importlib.util
import sqlite3
from pathlib import Path

import pytest

import tenant_manager


def _load_run05():
    path = Path(__file__).parent.parent.parent / "postgres" / "migrations" / "run_05_supplier_checkin.py"
    spec = importlib.util.spec_from_file_location("run_05_supplier_checkin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _supplier_columns(conn) -> set:
    rows = conn.execute("PRAGMA table_info(suppliers)").fetchall()
    return {r[1] for r in rows}


@pytest.mark.unit
@pytest.mark.database
def test_fresh_tenant_schema_has_checkin_column(test_db):
    import database

    with database.get_conn() as conn:
        assert "last_checkin_at" in _supplier_columns(conn)


@pytest.mark.unit
@pytest.mark.database
def test_runtime_default_schema_has_checkin_column():
    schema_sql = tenant_manager.TenantManager._get_default_schema(None)
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(schema_sql)
        conn.executescript(schema_sql)  # re-apply must not raise
        assert "last_checkin_at" in _supplier_columns(conn)
    finally:
        conn.close()


@pytest.mark.unit
def test_migrate_all_isolates_a_bad_schema_and_continues():
    run05 = _load_run05()
    applied = []

    def apply_fn(schema):
        if schema == "tenant_bad":
            raise RuntimeError("boom in this schema")
        applied.append(schema)

    ok, failed = run05.migrate_all(["tenant_a", "tenant_bad", "tenant_c"], apply_fn)

    assert ok == ["tenant_a", "tenant_c"]
    assert applied == ["tenant_a", "tenant_c"]
    assert len(failed) == 1 and failed[0][0] == "tenant_bad"


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
    run05 = _load_run05()
    conn = _FakeConn([("+5491153695627",), ("+14155550000",)])

    schemas = run05.enumerate_tenant_schemas(conn)

    assert "public" not in schemas
    assert len(schemas) == 2
    assert all(s.startswith("tenant_") for s in schemas), schemas


@pytest.mark.unit
def test_migration_statement_is_idempotent_add_column():
    run05 = _load_run05()
    assert len(run05.MIGRATION_STATEMENTS) == 1
    stmt = run05.MIGRATION_STATEMENTS[0]
    assert "ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS last_checkin_at" in stmt
