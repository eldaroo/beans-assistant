"""Unit tests for the M3.3 LLM-driven onboarding dispatcher.

Covers (from the M3.3 spec):
- Pure-text turn (no tool call): assistant text passes through.
- Tool call success: state mutates, metadata.captured carries the diff.
- Tool call validation error: state unchanged, status='failure'.
- LLM timeout: metadata.error == 'llm_unavailable'.
- Unknown tool name: silently skipped.
- Recursion cap: only the first 4 tool calls are dispatched.
- Confirm path: tenant row created, app_users row created, pending row gone.

Gemini is mocked at the LangChain level (the ``llm.invoke`` call); the
test never reaches the network. Postgres is real (the same container the
rest of the unit suite uses on :5433); each test uses a unique email and
cleans up its own rows on teardown.
"""

import os
import socket
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


# Pin the Postgres test container's port BEFORE importing the route.
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_DB", "beansco_main")
os.environ.setdefault("POSTGRES_USER", "beansco")
os.environ.setdefault("POSTGRES_PASSWORD", "changeme123")
os.environ.setdefault("SESSION_SECRET", "unit-test-secret-do-not-use-in-prod")
os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-real")


def _pg_reachable() -> bool:
    try:
        with socket.create_connection(
            (
                os.getenv("POSTGRES_HOST", "localhost"),
                int(os.getenv("POSTGRES_PORT", "5433")),
            ),
            timeout=0.5,
        ):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        not _pg_reachable(),
        reason="Postgres not reachable on :5433; skipping dispatcher tests.",
    ),
]


from fastapi.testclient import TestClient  # noqa: E402

from backend.repositories.pending_onboarding_repository import (  # noqa: E402
    PendingOnboardingRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeRepo:
    """Minimal app_users repo stub used by AuthService when minting cookies."""

    def __init__(self, users=None):
        self.users = users or {}

    def get_by_email(self, email):
        return self.users.get(email.lower())

    def update_last_login(self, _user_id):
        pass


def _pending_cookie(email: str, name: str = "Tester"):
    """Mint a real pending-session cookie via AuthService."""
    from backend.services.auth_service import SESSION_COOKIE_NAME, AuthService

    svc = AuthService(repo=_FakeRepo())
    token = svc.issue_pending_session(email=email, name=name, picture="")
    return {SESSION_COOKIE_NAME: token}


def _client():
    """A TestClient over the real FastAPI app."""
    from backend.app import app

    return TestClient(app)


def _make_ai_message(content: str = "", tool_calls: list | None = None):
    """Build a duck-typed AIMessage stand-in for a mocked llm.invoke."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    return msg


def _cleanup_email(email: str) -> None:
    """Best-effort: drop any pending row + tenant + app_user this email
    might have created during a test."""
    repo = PendingOnboardingRepository()
    try:
        repo.delete(email)
    except Exception:
        pass
    conn = repo._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.app_users WHERE google_email = %s",
                (email,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def _cleanup_phone(phone: str) -> None:
    """Wipe the tenant row + tenant schema + app_users row for a phone."""
    if not phone:
        return
    repo = PendingOnboardingRepository()
    conn = repo._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.app_users WHERE phone_number = %s",
                (phone,),
            )
            cur.execute(
                "DELETE FROM public.tenants WHERE phone_number = %s",
                (phone,),
            )
            # Drop the tenant schema if it exists.
            import re

            sanitized = re.sub(r"[^0-9A-Za-z]+", "_", phone.lstrip("+")).strip("_")
            schema = f"tenant_{sanitized}" if sanitized else "tenant_default"
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


@pytest.fixture
def fresh_email():
    return f"test-{uuid4()}@example.test"


@pytest.fixture
def cleanup():
    emails: list[str] = []
    phones: list[str] = []
    yield {"emails": emails, "phones": phones}
    for e in emails:
        _cleanup_email(e)
    for p in phones:
        _cleanup_phone(p)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_pure_text_turn_no_tool_calls(fresh_email, cleanup):
    """LLM responds with text only — no tool dispatch, state stays empty."""
    cleanup["emails"].append(fresh_email)

    bound = MagicMock()
    bound.invoke.return_value = _make_ai_message(content="Hola, ¿como te llamas?")
    fake_llm = MagicMock()
    fake_llm.bind_tools.return_value = bound

    with patch(
        "backend.api.onboarding_web._llm_for_tools_with_bindings",
        return_value=bound,
    ):
        client = _client()
        resp = client.post(
            "/api/onboarding/web",
            json={"message": "hola"},
            cookies=_pending_cookie(fresh_email),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"].startswith("Hola")
    assert body["metadata"]["tool_calls"] == []
    assert body["metadata"]["complete"] is False
    assert body["metadata"]["captured"] == {}
    assert body["metadata"]["redirect_to"] is None

    # State row exists and stays empty.
    row = PendingOnboardingRepository().get(fresh_email)
    assert row is not None
    assert row["state"] == {}


def test_tool_call_success_captures_field(fresh_email, cleanup):
    """Tool call for capture_business_name updates state + metadata.captured."""
    cleanup["emails"].append(fresh_email)

    first = _make_ai_message(
        tool_calls=[
            {
                "name": "capture_business_name",
                "args": {"name": "Cafe Catuai"},
                "id": "call_1",
            }
        ]
    )
    second = _make_ai_message(content="Listo, anote el nombre. ¿Y el WhatsApp?")
    bound = MagicMock()
    bound.invoke.side_effect = [first, second]

    with patch(
        "backend.api.onboarding_web._llm_for_tools_with_bindings",
        return_value=bound,
    ):
        client = _client()
        resp = client.post(
            "/api/onboarding/web",
            json={"message": "Cafe Catuai"},
            cookies=_pending_cookie(fresh_email),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "anote" in body["response"].lower()

    tcs = body["metadata"]["tool_calls"]
    assert len(tcs) == 1
    assert tcs[0]["tool"] == "capture_business_name"
    assert tcs[0]["status"] == "success"
    assert "Cafe Catuai" in tcs[0]["label_es"]

    assert body["metadata"]["captured"] == {"business_name": "Cafe Catuai"}

    row = PendingOnboardingRepository().get(fresh_email)
    assert row is not None
    assert row["state"]["business_name"] == "Cafe Catuai"


def test_tool_call_validation_error_keeps_state_unchanged(fresh_email, cleanup):
    """A capture_phone with bad format returns status=failure, state unchanged."""
    cleanup["emails"].append(fresh_email)

    first = _make_ai_message(
        tool_calls=[
            {
                "name": "capture_phone",
                "args": {"phone": "noplus"},
                "id": "call_p",
            }
        ]
    )
    second = _make_ai_message(content="Necesito el WhatsApp con + adelante.")
    bound = MagicMock()
    bound.invoke.side_effect = [first, second]

    with patch(
        "backend.api.onboarding_web._llm_for_tools_with_bindings",
        return_value=bound,
    ):
        client = _client()
        resp = client.post(
            "/api/onboarding/web",
            json={"message": "noplus"},
            cookies=_pending_cookie(fresh_email),
        )

    assert resp.status_code == 200
    body = resp.json()
    tcs = body["metadata"]["tool_calls"]
    assert len(tcs) == 1
    assert tcs[0]["tool"] == "capture_phone"
    assert tcs[0]["status"] == "failure"

    row = PendingOnboardingRepository().get(fresh_email)
    assert row is not None
    assert "phone" not in row["state"]


def test_llm_timeout_returns_llm_unavailable(fresh_email, cleanup):
    """First-call timeout produces metadata.error='llm_unavailable'."""
    cleanup["emails"].append(fresh_email)

    bound = MagicMock()

    def _hang(*_a, **_kw):
        import asyncio

        raise asyncio.TimeoutError("simulated")

    # Easier path: have invoke raise a synchronous error that the wait_for
    # surfaces as TimeoutError. Simpler: patch asyncio.wait_for itself.
    bound.invoke.return_value = _make_ai_message(content="ok")

    with patch(
        "backend.api.onboarding_web._llm_for_tools_with_bindings",
        return_value=bound,
    ), patch(
        "backend.api.onboarding_web.asyncio.wait_for",
        side_effect=__import__("asyncio").TimeoutError(),
    ):
        client = _client()
        resp = client.post(
            "/api/onboarding/web",
            json={"message": "hola"},
            cookies=_pending_cookie(fresh_email),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["metadata"]["error"] == "llm_unavailable"


def test_unknown_tool_name_is_silently_skipped(fresh_email, cleanup):
    """A tool call to a name not in TOOL_REGISTRY is dropped, no card emitted."""
    cleanup["emails"].append(fresh_email)

    first = _make_ai_message(
        tool_calls=[
            {"name": "capture_unknown", "args": {}, "id": "x"},
        ]
    )
    second = _make_ai_message(content="Sigamos.")
    bound = MagicMock()
    bound.invoke.side_effect = [first, second]

    with patch(
        "backend.api.onboarding_web._llm_for_tools_with_bindings",
        return_value=bound,
    ):
        client = _client()
        resp = client.post(
            "/api/onboarding/web",
            json={"message": "?"},
            cookies=_pending_cookie(fresh_email),
        )

    assert resp.status_code == 200
    body = resp.json()
    # Unknown tool produces no card.
    assert body["metadata"]["tool_calls"] == []


def test_recursion_cap_dispatches_at_most_four_calls(fresh_email, cleanup):
    """Six tool calls in one response collapse to four dispatched cards."""
    cleanup["emails"].append(fresh_email)

    # Use only known tools so each card actually executes.
    big_call = _make_ai_message(
        tool_calls=[
            {"name": "capture_business_name", "args": {"name": f"N{i}"}, "id": f"c{i}"}
            for i in range(6)
        ]
    )
    second = _make_ai_message(content="Hecho.")
    bound = MagicMock()
    bound.invoke.side_effect = [big_call, second]

    with patch(
        "backend.api.onboarding_web._llm_for_tools_with_bindings",
        return_value=bound,
    ):
        client = _client()
        resp = client.post(
            "/api/onboarding/web",
            json={"message": "spam"},
            cookies=_pending_cookie(fresh_email),
        )

    assert resp.status_code == 200
    tcs = resp.json()["metadata"]["tool_calls"]
    assert len(tcs) == 4


def test_confirm_path_creates_tenant_and_clears_pending(fresh_email, cleanup):
    """A complete state + confirm_and_create_tenant call drops a real
    tenant + app_users row, deletes the pending row, and surfaces
    redirect_to in metadata."""
    phone = f"+5491100{uuid4().int % 10_000_000:07d}"
    cleanup["emails"].append(fresh_email)
    cleanup["phones"].append(phone)

    # Seed the pending row with a complete state.
    repo = PendingOnboardingRepository()
    repo.upsert(
        email=fresh_email,
        state={
            "business_name": "Cafe del Centro",
            "phone": phone,
            "currency": "ARS",
            "language": "es",
            "owner_name": "Tester",
        },
        history=[],
        turn_count=4,
    )

    first = _make_ai_message(
        tool_calls=[
            {"name": "confirm_and_create_tenant", "args": {}, "id": "confirm"},
        ]
    )
    second = _make_ai_message(content="Listo, te llevo a tu negocio.")
    bound = MagicMock()
    bound.invoke.side_effect = [first, second]

    with patch(
        "backend.api.onboarding_web._llm_for_tools_with_bindings",
        return_value=bound,
    ):
        client = _client()
        resp = client.post(
            "/api/onboarding/web",
            json={"message": "dale"},
            cookies=_pending_cookie(fresh_email),
        )

    assert resp.status_code == 200
    body = resp.json()

    assert body["metadata"]["complete"] is True
    assert body["metadata"]["redirect_to"] == f"/tenants/{phone}"

    tcs = body["metadata"]["tool_calls"]
    assert len(tcs) == 1
    assert tcs[0]["tool"] == "confirm_and_create_tenant"
    assert tcs[0]["status"] == "success"

    # Pending row should be gone.
    assert PendingOnboardingRepository().get(fresh_email) is None

    # tenants row exists.
    conn = PendingOnboardingRepository()._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT business_name FROM public.tenants WHERE phone_number = %s",
                (phone,),
            )
            row = cur.fetchone()
            assert row is not None
            assert row["business_name"] == "Cafe del Centro"

            cur.execute(
                "SELECT role FROM public.app_users WHERE google_email = %s",
                (fresh_email,),
            )
            user_row = cur.fetchone()
            assert user_row is not None
            assert user_row["role"] == "owner"
    finally:
        conn.close()
