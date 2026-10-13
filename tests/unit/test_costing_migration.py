"""Costing migration tests (spec 003 M2, AC6).

AC6: applying the costing migration (create_tenant_schema plus a forward loop over
public.tenants) creates all ten costing tables on a fresh AND on an existing
seeded tenant schema; a test asserts each table per schema and that one bad schema
does not abort the loop.

The repo's DB tests run on SQLite, so these verify (against SQLite):
  - the ten tables exist after the standard schema load (a fresh tenant);
  - an existing seeded schema (products + data, no costing tables) GAINS the ten
    costing tables when the DDL is applied, with its data untouched (the honest
    existing-tenant path, the SQLite analog of run_03);
  - the runtime DDL is idempotent (re-applying over a schema that already has the
    tables is a no-op, not an error);
  - the forward-loop control flow isolates a failing schema and continues (the
    "one bad schema does not abort the loop" guarantee), and the target set is
    tenant-only (public is never a target) — both against the real functions with
    no DB dependency;
  - the Postgres migration statements are all CREATE TABLE IF NOT EXISTS and cover
    exactly the ten named tables.
NOT proven here: run_03's Postgres DDL executed against a real existing Postgres
tenant schema (the exact bytes, FK resolution against a live products table). That
needs a Postgres scratch DB (the SCRATCH_DB_URL the develop gate already names) and
is exercised at deploy time by run_03 (with its validating --dry-run first).
"""
import importlib.util
import sqlite3
from pathlib import Path

import pytest

import tenant_manager

COSTING_TABLES = {
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
}


def _load_run03():
    path = Path(__file__).parent.parent.parent / "postgres" / "migrations" / "run_03_costing_tables.py"
    spec = importlib.util.spec_from_file_location("run_03_costing_tables", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tables_in(conn) -> set:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


# ---------------------------------------------------------------- AC6 fresh

@pytest.mark.unit
@pytest.mark.database
def test_fresh_tenant_schema_has_all_ten_costing_tables(test_db):
    """The ten costing tables exist on a freshly provisioned schema."""
    import database

    with database.get_conn() as conn:
        tables = _tables_in(conn)
    missing = COSTING_TABLES - tables
    assert not missing, f"costing tables missing from a fresh schema: {sorted(missing)}"


# ------------------------------------------------- AC6 existing-schema idempotency

@pytest.mark.unit
@pytest.mark.database
def test_existing_seeded_schema_gains_costing_tables_without_disturbing_data():
    """An existing M1 tenant (products + data, no costing tables) gains the ten
    costing tables when the runtime DDL is applied, and its seeded data survives.
    The SQLite analog of run_03 adding the tables to an already-provisioned tenant."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(
            "CREATE TABLE products ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  sku TEXT NOT NULL UNIQUE,"
            "  name TEXT NOT NULL,"
            "  description TEXT,"
            "  unit_cost_cents INTEGER NOT NULL DEFAULT 0,"
            "  unit_price_cents INTEGER,"
            "  is_active INTEGER NOT NULL DEFAULT 1,"
            "  created_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ");"
        )
        conn.execute(
            "INSERT INTO products (sku, name, unit_cost_cents, unit_price_cents) "
            "VALUES ('BC-X', 'Pulsera X', 400, 1200)"
        )
        conn.commit()
        before = _tables_in(conn)
        assert COSTING_TABLES.isdisjoint(before), "precondition: no costing tables yet"

        # Apply the runtime schema DDL over the existing (seeded) schema.
        conn.executescript(tenant_manager.TenantManager._get_default_schema(None))

        after = _tables_in(conn)
        missing = COSTING_TABLES - after
        assert not missing, f"existing schema did not gain costing tables: {sorted(missing)}"
        rows = conn.execute("SELECT sku FROM products").fetchall()
        assert [r[0] for r in rows] == ["BC-X"], "existing product data must be untouched"
    finally:
        conn.close()


@pytest.mark.unit
@pytest.mark.database
def test_runtime_schema_is_idempotent_on_an_existing_schema():
    """Re-applying the SQLite runtime schema to a schema that already has the
    costing tables is a no-op (CREATE TABLE IF NOT EXISTS), never an error."""
    schema_sql = tenant_manager.TenantManager._get_default_schema(None)
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(schema_sql)  # fresh
        conn.executescript(schema_sql)  # existing seeded schema: must not raise
        tables = _tables_in(conn)
    finally:
        conn.close()
    missing = COSTING_TABLES - tables
    assert not missing, f"costing tables missing after idempotent re-apply: {sorted(missing)}"


# ----------------------------------------------- AC6 one bad schema does not abort

@pytest.mark.unit
def test_migrate_all_isolates_a_bad_schema_and_continues():
    run03 = _load_run03()
    applied = []

    def apply_fn(schema):
        if schema == "tenant_bad":
            raise RuntimeError("boom in this schema")
        applied.append(schema)

    ok, failed = run03.migrate_all(["tenant_a", "tenant_bad", "tenant_c"], apply_fn)

    assert ok == ["tenant_a", "tenant_c"], "the good schemas must migrate"
    assert applied == ["tenant_a", "tenant_c"], "the loop must continue past the bad schema"
    assert len(failed) == 1 and failed[0][0] == "tenant_bad"
    assert "boom" in failed[0][1]


# --------------------------------------------- AC6 statements shape and coverage

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
    """The forward loop targets tenant schemas only. public holds no products
    table and the costing tables carry REFERENCES products(id), so public must
    never be in the target set (the HIGH the council caught: a prepended public
    fails every run)."""
    run03 = _load_run03()
    conn = _FakeConn([("+5491153695627",), ("+14155550000",)])

    schemas = run03.enumerate_tenant_schemas(conn)

    assert "public" not in schemas, "public must never be a migration target"
    assert len(schemas) == 2
    assert all(s.startswith("tenant_") for s in schemas), schemas


@pytest.mark.unit
def test_migration_statements_are_idempotent_and_cover_ten_tables():
    run03 = _load_run03()

    assert len(run03.COSTING_TABLE_NAMES) == 10
    assert set(run03.COSTING_TABLE_NAMES) == COSTING_TABLES
    assert len(run03.MIGRATION_STATEMENTS) == 10

    for stmt in run03.MIGRATION_STATEMENTS:
        assert "CREATE TABLE IF NOT EXISTS" in stmt, "every statement must be idempotent"

    joined = "\n".join(run03.MIGRATION_STATEMENTS)
    for name in COSTING_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {name}" in joined, f"no statement creates {name}"
