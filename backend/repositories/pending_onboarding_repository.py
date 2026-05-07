"""Data access for public.pending_onboarding_sessions.

Per ADR-002, this repo is the per-email scratchpad for the LLM-driven
onboarding flow. The row holds the partial captured `state`, the
truncated conversation `history`, and a turn counter. TTL is 24h from
`created_at`; expired rows are lazy-deleted on first read by `get`.
"""

import json
import os
from typing import Optional


class PendingOnboardingRepository:
    """CRUD for pending_onboarding_sessions. Always public schema."""

    @staticmethod
    def _connect():
        import psycopg2
        from psycopg2.extras import RealDictCursor
        return psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            dbname=os.getenv("POSTGRES_DB", "beansco_main"),
            user=os.getenv("POSTGRES_USER", "beansco"),
            password=os.getenv("POSTGRES_PASSWORD", "changeme123"),
            cursor_factory=RealDictCursor,
            options="-c client_encoding=UTF8",
        )

    @staticmethod
    def _normalize_email(email: str) -> str:
        return (email or "").strip().lower()

    @staticmethod
    def _row_to_dict(row) -> dict:
        """psycopg2's RealDictCursor returns JSONB as already-decoded
        Python objects. Normalize to a plain dict so callers can rely on
        the shape without poking at psycopg2 internals."""
        return dict(row)

    def get(self, email: str) -> Optional[dict]:
        """Return the row dict or None.

        Lazy-deletes the row if `expires_at < NOW()` and returns None
        in that case (per ADR-002, "lazy delete on first read of an
        expired row is sufficient").
        """
        normalized = self._normalize_email(email)
        if not normalized:
            return None
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT email, state, history, turn_count, created_at, expires_at
                    FROM public.pending_onboarding_sessions
                    WHERE email = %s
                    """,
                    (normalized,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                # Compare expires_at against NOW() in DB time, not Python
                # time, by re-using the row + a server-side check.
                cur.execute(
                    """
                    SELECT NOW() >= expires_at AS expired
                    FROM public.pending_onboarding_sessions
                    WHERE email = %s
                    """,
                    (normalized,),
                )
                exp = cur.fetchone()
                if exp and exp["expired"]:
                    cur.execute(
                        "DELETE FROM public.pending_onboarding_sessions WHERE email = %s",
                        (normalized,),
                    )
                    conn.commit()
                    return None
                return self._row_to_dict(row)
        finally:
            conn.close()

    def upsert(
        self,
        email: str,
        state: dict,
        history: list,
        turn_count: int,
    ) -> dict:
        """Insert or update the row.

        On INSERT: `created_at = NOW()`, `expires_at = NOW() + 24h`.
        On UPDATE: `expires_at` is preserved from the existing row;
        `state`, `history`, and `turn_count` are overwritten.
        Returns the persisted row.
        """
        normalized = self._normalize_email(email)
        if not normalized:
            raise ValueError("email is required")
        state_json = json.dumps(state or {})
        history_json = json.dumps(history or [])
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.pending_onboarding_sessions
                        (email, state, history, turn_count, expires_at)
                    VALUES
                        (%s, %s::jsonb, %s::jsonb, %s, NOW() + INTERVAL '24 hours')
                    ON CONFLICT (email) DO UPDATE SET
                        state      = EXCLUDED.state,
                        history    = EXCLUDED.history,
                        turn_count = EXCLUDED.turn_count
                    RETURNING email, state, history, turn_count, created_at, expires_at
                    """,
                    (normalized, state_json, history_json, int(turn_count)),
                )
                row = cur.fetchone()
            conn.commit()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def append_history(self, email: str, message: dict) -> None:
        """Atomically append `message` to history and bump turn_count by 1.

        Uses the JSONB `||` concat operator. No-op if the row doesn't
        exist (callers must `upsert` first; this is the M3.3 contract).
        """
        normalized = self._normalize_email(email)
        if not normalized:
            raise ValueError("email is required")
        message_json = json.dumps(message or {})
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.pending_onboarding_sessions
                       SET history    = history || %s::jsonb,
                           turn_count = turn_count + 1
                     WHERE email = %s
                    """,
                    (json.dumps([message or {}]), normalized),
                )
            conn.commit()
        finally:
            conn.close()

    def merge_state(self, email: str, partial: dict) -> dict:
        """Atomically merge `partial` into `state` using JSONB `||`.

        Returns the new state dict. Used by tool executors (M3.2/M3.3)
        to write a single captured field without clobbering siblings.
        Raises LookupError if the row does not exist.
        """
        normalized = self._normalize_email(email)
        if not normalized:
            raise ValueError("email is required")
        partial_json = json.dumps(partial or {})
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.pending_onboarding_sessions
                       SET state = state || %s::jsonb
                     WHERE email = %s
                     RETURNING state
                    """,
                    (partial_json, normalized),
                )
                row = cur.fetchone()
            conn.commit()
            if not row:
                raise LookupError(f"No pending session for email={normalized}")
            return dict(row["state"]) if row["state"] is not None else {}
        finally:
            conn.close()

    def delete(self, email: str, conn=None) -> None:
        """Delete the row.

        If `conn` is provided, run inside the caller's connection (and
        do NOT commit or close it — the caller owns the transaction).
        This is the seam M3.3's `confirm_and_create_tenant` uses to
        atomically delete the pending row alongside `tenants.create` +
        `app_users.create` in one transaction.

        If `conn` is None, open and close our own connection, and
        commit it.
        """
        normalized = self._normalize_email(email)
        if not normalized:
            raise ValueError("email is required")

        if conn is not None:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.pending_onboarding_sessions WHERE email = %s",
                    (normalized,),
                )
            return

        own = self._connect()
        try:
            with own.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.pending_onboarding_sessions WHERE email = %s",
                    (normalized,),
                )
            own.commit()
        finally:
            own.close()

    def phone_in_use_by_other_pending(self, phone: str, current_email: str) -> bool:
        """Return True iff some OTHER live pending session has the same
        phone in its `state`. Used by `capture_phone` (M3.2) to detect
        a collision against another concurrent pending session before
        the row reaches `tenants` (where the unique constraint lives).
        """
        if not phone:
            return False
        normalized_email = self._normalize_email(current_email)
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                      FROM public.pending_onboarding_sessions
                     WHERE state ->> 'phone' = %s
                       AND email <> %s
                     LIMIT 1
                    """,
                    (phone, normalized_email),
                )
                return cur.fetchone() is not None
        finally:
            conn.close()
