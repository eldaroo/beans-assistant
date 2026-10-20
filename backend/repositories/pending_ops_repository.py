"""The pending-operation store for two-phase writes (spec 007 M3, D-038/D-043).

A write tool never commits. It stages a validated preview here under an ``op_token``;
the non-model ``/chat/confirm`` endpoint is the only thing that commits it. The store is
DB-backed (not in-process) on purpose: the gateway's tool callback and the browser's
confirm can land on different command-center workers, and the row must survive a restart,
so an in-memory dict would lose or split the pending op. It lives in the tenant schema, so
it is tenant-scoped by construction.

Lifecycle of a row: staged PENDING with ``auto`` NULL (verdict not yet computed) → the app
computes the auto verdict and sets ``auto``/``requires_human_review`` → ``/chat/confirm``
flips it to COMMITTED once (idempotent: a second confirm is a no-op) and records the
commit result → the Undo system path flips it to CANCELLED.

Runs under the caller's tenant_context (uses the tenant-scoped db helpers).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from database_config import execute, fetch_all, fetch_one


def _ph() -> str:
    import database_config

    return "%s" if getattr(database_config, "USE_POSTGRES", False) else "?"


def _q(sql: str) -> str:
    """Rewrite %s placeholders to the active backend's placeholder."""
    ph = _ph()
    return sql if ph == "%s" else sql.replace("%s", ph)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def ensure_table() -> None:
    """Create the pending_ops table if the tenant schema does not have it yet.

    Idempotent (CREATE TABLE IF NOT EXISTS). DDL portable across Postgres and SQLite:
    TEXT primary key, integer booleans (0/1, NULL = verdict pending), TEXT JSON columns,
    app-written ISO timestamps (not DB CURRENT_TIMESTAMP) so turn-window comparisons are
    clock-skew-free."""
    execute(
        """
        CREATE TABLE IF NOT EXISTS pending_ops (
            op_token TEXT PRIMARY KEY,
            operation_type TEXT NOT NULL,
            args TEXT NOT NULL,
            utterance TEXT,
            product_name TEXT,
            candidate_count INTEGER,
            turn_nonce TEXT,
            auto INTEGER,
            requires_human_review INTEGER,
            status TEXT NOT NULL DEFAULT 'PENDING',
            commit_result TEXT,
            reasons TEXT,
            created_at TEXT NOT NULL,
            committed_at TEXT
        )
        """
    )
    # Backfill the turn_nonce column on an older table (idempotent; ignore if it exists).
    try:
        execute("ALTER TABLE pending_ops ADD COLUMN turn_nonce TEXT")
    except Exception:
        pass


def stage(
    *,
    op_token: str,
    operation_type: str,
    args: dict,
    utterance: str | None,
    product_name: str | None,
    candidate_count: int | None,
    turn_nonce: str | None = None,
) -> str:
    """Insert a PENDING op with the verdict not yet computed (auto NULL). Returns created_at.

    ``turn_nonce`` identifies the agent turn that staged this op (pinned out of band, D-037),
    so the app correlates a staged write to THIS turn by identity, not by wall-clock — closing
    the concurrent-turn / compound-turn hole the council flagged (Winston/Amelia/Edut)."""
    ensure_table()
    created_at = _utcnow_iso()
    execute(
        _q(
            """
            INSERT INTO pending_ops
                (op_token, operation_type, args, utterance, product_name,
                 candidate_count, turn_nonce, auto, requires_human_review, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL, 'PENDING', %s)
            """
        ),
        (
            op_token,
            operation_type,
            json.dumps(args),
            utterance,
            product_name,
            candidate_count,
            turn_nonce,
            created_at,
        ),
    )
    return created_at


def set_verdict(op_token: str, *, auto: bool, requires_human_review: bool, reasons: list[str]) -> None:
    execute(
        _q("UPDATE pending_ops SET auto = %s, requires_human_review = %s, reasons = %s WHERE op_token = %s"),
        (1 if auto else 0, 1 if requires_human_review else 0, json.dumps(reasons), op_token),
    )


def get(op_token: str) -> dict | None:
    # Ensure the table exists so a confirm against a DB where nothing was ever staged
    # returns None (unknown op), not an OperationalError.
    try:
        ensure_table()
    except Exception:
        return None
    row = fetch_one(_q("SELECT * FROM pending_ops WHERE op_token = %s"), (op_token,))
    if not row:
        return None
    d = dict(row)
    for k in ("args", "commit_result", "reasons"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except (TypeError, ValueError):
                pass
    return d


def claim(op_token: str) -> bool:
    """Atomically transition PENDING -> COMMITTING. Returns True for the single winner.

    This is the claim-before-commit guard (council B1/H2): the real write runs only for the
    caller that wins this conditional UPDATE, so two concurrent confirms of one op_token can
    never both post. A loser gets False and must re-read (the winner will have committed)."""
    n = execute(
        _q("UPDATE pending_ops SET status = 'COMMITTING' WHERE op_token = %s AND status = 'PENDING'"),
        (op_token,),
    )
    return bool(n)


def unclaim(op_token: str) -> None:
    """Revert COMMITTING -> PENDING when the commit is rejected by a guard (pessimistic post),
    so a later retry (e.g. after stock is added) can claim and commit it again."""
    execute(
        _q("UPDATE pending_ops SET status = 'PENDING' WHERE op_token = %s AND status = 'COMMITTING'"),
        (op_token,),
    )


def mark_committed(op_token: str, commit_result: dict) -> bool:
    """Finalize COMMITTING -> COMMITTED, recording the commit result. Returns True on the
    transition (the claimer), False otherwise."""
    n = execute(
        _q(
            """
            UPDATE pending_ops
            SET status = 'COMMITTED', commit_result = %s, committed_at = %s
            WHERE op_token = %s AND status = 'COMMITTING'
            """
        ),
        (json.dumps(commit_result), _utcnow_iso(), op_token),
    )
    return bool(n)


def claim_cancel(op_token: str) -> bool:
    """Atomically transition COMMITTED -> CANCELLING for the Undo path. Returns True for the
    single winner, so a double Undo tap compensates at most once regardless of whether the
    underlying cancel_* function is itself idempotent (council H4)."""
    n = execute(
        _q("UPDATE pending_ops SET status = 'CANCELLING' WHERE op_token = %s AND status = 'COMMITTED'"),
        (op_token,),
    )
    return bool(n)


def finalize_cancelled(op_token: str) -> None:
    execute(
        _q("UPDATE pending_ops SET status = 'CANCELLED' WHERE op_token = %s AND status = 'CANCELLING'"),
        (op_token,),
    )


def revert_cancel(op_token: str) -> None:
    """Revert CANCELLING -> COMMITTED if the compensator failed, so Undo can be retried."""
    execute(
        _q("UPDATE pending_ops SET status = 'COMMITTED' WHERE op_token = %s AND status = 'CANCELLING'"),
        (op_token,),
    )


def _hydrate(row) -> dict:
    d = dict(row)
    for k in ("args", "commit_result", "reasons"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except (TypeError, ValueError):
                pass
    return d


def verdict_pending_for_turn(turn_nonce: str) -> list[dict]:
    """Every op this turn staged whose verdict is not yet computed (auto IS NULL, PENDING),
    correlated by the turn nonce — NOT by wall-clock. Returns a list so a compound turn
    (one message that stages, e.g., a sale AND an expense) surfaces every staged write
    instead of silently dropping all but the newest (council H3). Oldest first."""
    if not turn_nonce:
        return []
    try:
        ensure_table()
    except Exception:
        return []
    rows = fetch_all(
        _q(
            "SELECT * FROM pending_ops WHERE turn_nonce = %s AND status = 'PENDING' "
            "AND auto IS NULL ORDER BY created_at ASC"
        ),
        (turn_nonce,),
    )
    return [_hydrate(r) for r in (rows or [])]
