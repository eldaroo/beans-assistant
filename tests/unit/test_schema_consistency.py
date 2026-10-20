"""Schema-consistency guard (spec 007 M3, council: Amelia B1/M6).

The expense void appends a POSITIVE row tagged CANCELACION and relies on the expenses_total
view to SUBTRACT that category. That view is defined in several places; fixing some and
missing others silently inverts the void at runtime (profit moves the wrong way) while a test
loading only the fixed schema stays green — exactly the false-green this guard prevents.

Every runtime definition of expenses_total MUST carry the CANCELACION CASE.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

SCHEMA_SOURCES = [
    "database_pg.py",
    "tenant_manager.py",
    "postgres/init/01-schema.sql",
    "root_archive/init_complete_database.sql",
]


@pytest.mark.parametrize("rel", SCHEMA_SOURCES)
def test_expenses_total_subtracts_cancelacion(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert "expenses_total AS" in text, f"{rel} should define the expenses_total view"
    # Locate the view BODY (…expenses_total AS …), not an earlier DROP VIEW statement.
    idx = text.index("expenses_total AS")
    window = text[idx: idx + 400]
    assert re.search(r"CANCELACION", window), (
        f"{rel}: expenses_total must subtract the CANCELACION category "
        f"(CASE WHEN category = 'CANCELACION' THEN -amount_cents ...), else the expense void inverts"
    )
