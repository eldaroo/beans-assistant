"""Unit tests for PendingOnboardingRepository.

These tests run against the real Postgres on :5433 (the `beans-pg-test`
container that already hosts the rest of the public-schema tables).
Each test uses a unique email per run (`f"test-{uuid4()}@example"`)
so collisions with real data or sibling tests are impossible.
Each test cleans up its own row at the end.
"""

import os
import socket
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

# Force the test container's port BEFORE importing the repo, so the
# psycopg2 connect call in `_connect()` reads the right env.
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_DB", "beansco_main")
os.environ.setdefault("POSTGRES_USER", "beansco")
os.environ.setdefault("POSTGRES_PASSWORD", "changeme123")


def _pg_reachable() -> bool:
    try:
        with socket.create_connection(
            (os.getenv("POSTGRES_HOST", "localhost"), int(os.getenv("POSTGRES_PORT", "5433"))),
            timeout=0.5,
        ):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.unit,
    pytest.mark.database,
    pytest.mark.skipif(
        not _pg_reachable(),
        reason="Postgres not reachable on :5433; skipping pending onboarding repo tests.",
    ),
]


from backend.repositories.pending_onboarding_repository import (  # noqa: E402
    PendingOnboardingRepository,
)


@pytest.fixture
def repo():
    return PendingOnboardingRepository()


@pytest.fixture
def fresh_email():
    """A unique email per test invocation."""
    return f"test-{uuid4()}@example.test"


@pytest.fixture
def cleanup(repo):
    """Track emails to delete at teardown."""
    emails: list[str] = []
    yield emails
    for email in emails:
        try:
            repo.delete(email)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_nonexistent_returns_none(repo, fresh_email):
    assert repo.get(fresh_email) is None


def test_get_lazy_deletes_expired_row(repo, fresh_email, cleanup):
    """If a row's expires_at is in the past, get() must delete it and return None."""
    cleanup.append(fresh_email)
    # Insert via raw SQL so we can force an expired row (the repo's upsert
    # always sets expires_at to NOW() + 24h, which is by design).
    conn = repo._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.pending_onboarding_sessions
                    (email, state, history, turn_count, created_at, expires_at)
                VALUES
                    (%s, '{}'::jsonb, '[]'::jsonb, 0,
                     NOW() - INTERVAL '2 hours',
                     NOW() - INTERVAL '1 hour')
                """,
                (fresh_email,),
            )
        conn.commit()
    finally:
        conn.close()

    # Sanity: row exists raw.
    conn = repo._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM public.pending_onboarding_sessions WHERE email = %s",
                (fresh_email,),
            )
            assert cur.fetchone() is not None
    finally:
        conn.close()

    # get() must return None and remove the row.
    assert repo.get(fresh_email) is None

    conn = repo._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM public.pending_onboarding_sessions WHERE email = %s",
                (fresh_email,),
            )
            assert cur.fetchone() is None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


def test_upsert_inserts_fresh_row_with_24h_expiry(repo, fresh_email, cleanup):
    cleanup.append(fresh_email)

    row = repo.upsert(fresh_email, state={}, history=[], turn_count=0)

    assert row["email"] == fresh_email
    assert row["state"] == {}
    assert row["history"] == []
    assert row["turn_count"] == 0
    assert row["created_at"] is not None
    assert row["expires_at"] is not None

    delta = row["expires_at"] - row["created_at"]
    # 24h, give or take a few seconds for clock drift between INSERT
    # and the RETURNING evaluation.
    assert timedelta(hours=23, minutes=59, seconds=50) <= delta <= timedelta(hours=24, minutes=0, seconds=10)


def test_upsert_updates_without_resetting_expires_at(repo, fresh_email, cleanup):
    cleanup.append(fresh_email)

    first = repo.upsert(fresh_email, state={"business_name": "Bitácora"}, history=[], turn_count=0)
    original_expires_at = first["expires_at"]
    original_created_at = first["created_at"]

    second = repo.upsert(
        fresh_email,
        state={"business_name": "Bitácora", "phone": "+5491122334455"},
        history=[{"role": "user", "content": "hola"}],
        turn_count=1,
    )

    assert second["state"] == {"business_name": "Bitácora", "phone": "+5491122334455"}
    assert second["history"] == [{"role": "user", "content": "hola"}]
    assert second["turn_count"] == 1
    # expires_at and created_at must be preserved across UPDATE.
    assert second["expires_at"] == original_expires_at
    assert second["created_at"] == original_created_at


# ---------------------------------------------------------------------------
# merge_state
# ---------------------------------------------------------------------------


def test_merge_state_is_additive(repo, fresh_email, cleanup):
    cleanup.append(fresh_email)
    repo.upsert(
        fresh_email,
        state={"business_name": "Bitácora", "currency": "ARS"},
        history=[],
        turn_count=0,
    )

    new_state = repo.merge_state(fresh_email, {"phone": "+5491100000001"})

    # Existing keys survive; new key added.
    assert new_state == {
        "business_name": "Bitácora",
        "currency": "ARS",
        "phone": "+5491100000001",
    }

    # Subsequent merge replaces only its own keys.
    new_state_2 = repo.merge_state(fresh_email, {"currency": "USD"})
    assert new_state_2 == {
        "business_name": "Bitácora",
        "currency": "USD",
        "phone": "+5491100000001",
    }


def test_merge_state_raises_on_missing_row(repo, fresh_email):
    with pytest.raises(LookupError):
        repo.merge_state(fresh_email, {"x": 1})


# ---------------------------------------------------------------------------
# append_history
# ---------------------------------------------------------------------------


def test_append_history_appends_and_bumps_turn_count(repo, fresh_email, cleanup):
    cleanup.append(fresh_email)
    repo.upsert(fresh_email, state={}, history=[], turn_count=0)

    repo.append_history(fresh_email, {"role": "user", "content": "hola"})
    repo.append_history(fresh_email, {"role": "assistant", "content": "hola, capitán"})

    row = repo.get(fresh_email)
    assert row is not None
    assert row["history"] == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "hola, capitán"},
    ]
    assert row["turn_count"] == 2


# ---------------------------------------------------------------------------
# phone_in_use_by_other_pending
# ---------------------------------------------------------------------------


def test_phone_in_use_returns_true_for_other_email(repo, cleanup):
    email_a = f"test-{uuid4()}@example.test"
    email_b = f"test-{uuid4()}@example.test"
    cleanup.extend([email_a, email_b])

    repo.upsert(email_a, state={"phone": "+5491100000099"}, history=[], turn_count=0)

    # b has not claimed this phone yet — but a has, and a is "other" relative to b.
    assert repo.phone_in_use_by_other_pending("+5491100000099", email_b) is True


def test_phone_in_use_returns_false_for_same_email(repo, fresh_email, cleanup):
    cleanup.append(fresh_email)
    repo.upsert(fresh_email, state={"phone": "+5491100000098"}, history=[], turn_count=0)

    # If the same email already claimed this phone, it's not a collision
    # with itself — return False.
    assert repo.phone_in_use_by_other_pending("+5491100000098", fresh_email) is False


def test_phone_in_use_returns_false_when_no_match(repo, fresh_email, cleanup):
    cleanup.append(fresh_email)
    repo.upsert(fresh_email, state={"phone": "+5491100000097"}, history=[], turn_count=0)

    assert repo.phone_in_use_by_other_pending("+5491199999999", fresh_email) is False


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_removes_the_row(repo, fresh_email):
    repo.upsert(fresh_email, state={"x": 1}, history=[], turn_count=0)
    assert repo.get(fresh_email) is not None

    repo.delete(fresh_email)

    assert repo.get(fresh_email) is None


def test_delete_with_external_connection_does_not_commit(repo, fresh_email, cleanup):
    """When a caller passes its own connection, delete() must NOT commit
    or close it. The caller owns the transaction (M3.3 atomicity)."""
    cleanup.append(fresh_email)
    repo.upsert(fresh_email, state={"x": 1}, history=[], turn_count=0)

    conn = repo._connect()
    try:
        repo.delete(fresh_email, conn=conn)
        # Connection is still open and uncommitted: a fresh connection
        # should still see the row.
        check = repo._connect()
        try:
            with check.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM public.pending_onboarding_sessions WHERE email = %s",
                    (fresh_email,),
                )
                assert cur.fetchone() is not None
        finally:
            check.close()

        # Now caller commits — row goes away.
        conn.commit()

        check = repo._connect()
        try:
            with check.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM public.pending_onboarding_sessions WHERE email = %s",
                    (fresh_email,),
                )
                assert cur.fetchone() is None
        finally:
            check.close()
    finally:
        conn.close()
