"""Audit log + tool-call rate limits for the operation API (spec 007 M4, AC12).

Every tool call and every write intent is written to an append-only, tenant-scoped audit
table, and per-tenant tool-call caps hold — tighter on the destructive cancel/deactivate
ops. Both run under the caller's tenant_context (tenant-scoped table, via the db helpers).

The caps are a floor against a hijacked model or a runaway loop spamming the operation API;
they are deliberately generous for normal use and tight only where a write is destructive.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from database_config import execute, fetch_one

# Rolling window and caps. "session" here is the single business (tenant-scoped), which is
# the session boundary for a single-business deployment.
WINDOW_SECONDS = 60
GLOBAL_CAP = 60              # all tool calls per tenant per window
DESTRUCTIVE_CAP = 8         # cancel_* / deactivate per tenant per window (tighter)
DESTRUCTIVE_OPS = frozenset({
    "cancel_last_operation", "cancel_sale", "cancel_expense", "cancel_stock_movement",
    "deactivate_product",
})


def _ph() -> str:
    import database_config

    return "%s" if getattr(database_config, "USE_POSTGRES", False) else "?"


def _q(sql: str) -> str:
    ph = _ph()
    return sql if ph == "%s" else sql.replace("%s", ph)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def ensure_table() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS tool_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            args TEXT,
            caller TEXT,
            op_token TEXT,
            outcome TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
        if not _is_pg() else
        """
        CREATE TABLE IF NOT EXISTS tool_audit (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            args TEXT,
            caller TEXT,
            op_token TEXT,
            outcome TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


def _is_pg() -> bool:
    import database_config

    return bool(getattr(database_config, "USE_POSTGRES", False))


def audit(name: str, *, args=None, caller: str = "gateway", op_token: str | None = None,
          outcome: str = "ok") -> None:
    """Append one audit row. Never raises into the caller (a lost audit row must not
    sink a real operation, but it is logged)."""
    try:
        ensure_table()
        execute(
            _q(
                "INSERT INTO tool_audit (name, args, caller, op_token, outcome, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)"
            ),
            (name, json.dumps(args) if args is not None else None, caller, op_token,
             outcome, _iso(_utcnow())),
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("tool_audit append failed (non-fatal)")


def within_caps(op_name: str) -> bool:
    """True if a call to op_name is within the per-tenant window caps. Counts prior audit
    rows in the window; the destructive cap is checked against destructive rows only."""
    try:
        ensure_table()
    except Exception:
        # Fail CLOSED for the destructive ops (the floor must not evaporate under DB stress);
        # fail open for the rest, where the two-phase commit still gates every write.
        return op_name not in DESTRUCTIVE_OPS
    since = _iso(_utcnow() - timedelta(seconds=WINDOW_SECONDS))
    row = fetch_one(_q("SELECT COUNT(*) AS c FROM tool_audit WHERE created_at >= %s"), (since,))
    total = (row["c"] if row else 0) or 0
    if total >= GLOBAL_CAP:
        return False
    if op_name in DESTRUCTIVE_OPS:
        names = "('" + "','".join(sorted(DESTRUCTIVE_OPS)) + "')"
        drow = fetch_one(
            _q(f"SELECT COUNT(*) AS c FROM tool_audit WHERE created_at >= %s AND name IN {names}"),
            (since,),
        )
        dtotal = (drow["c"] if drow else 0) or 0
        if dtotal >= DESTRUCTIVE_CAP:
            return False
    return True
