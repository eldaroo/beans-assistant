"""Tests for onboarding M2.

Covers:
  - The /api/onboarding/web endpoint gating: no session, active session, pending.
  - The /api/onboarding/web stub branching: business trigger vs everything else.
  - The /onboarding page rendering for pending sessions and rejection otherwise.

JS-land tests for the chat factory are not run here — this codebase uses
pytest only and has no jest/vitest harness. The localStorage no-touch
behavior in onboarding mode is covered by E2E (TODO).
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch):
    """All tests need a session secret to mint cookies."""
    monkeypatch.setenv("SESSION_SECRET", "unit-test-secret-do-not-use-in-prod")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

class _FakeRepo:
    """Minimal app_users repo stub (M1 tests use the same shape)."""

    def __init__(self, users=None):
        self.users = users or {}
        self.last_login_calls = []

    def get_by_email(self, email):
        return self.users.get(email.lower())

    def update_last_login(self, user_id):
        self.last_login_calls.append(user_id)


def _pending_cookie(email="newcomer@gmail.com", name="Newcomer"):
    """Mint a pending-session cookie via the real AuthService."""
    from backend.services.auth_service import SESSION_COOKIE_NAME, AuthService

    svc = AuthService(repo=_FakeRepo())
    token = svc.issue_pending_session(email=email, name=name, picture="")
    return {SESSION_COOKIE_NAME: token}


def _active_cookie(role="owner", phone="+5491100000001", email="owner@gmail.com"):
    """Mint an active-session cookie (post-onboarding user)."""
    from backend.services.auth_service import SESSION_COOKIE_NAME, AuthService

    svc = AuthService(repo=_FakeRepo())
    token = svc.issue_session(
        {"id": 1, "google_email": email, "phone_number": phone, "role": role}
    )
    return {SESSION_COOKIE_NAME: token}


@pytest.fixture
def app_client():
    """A TestClient over the real app, with an in-memory tenants service so
    the import of `app.py` does not blow up on missing DB at module-load."""
    # Import here so the SESSION_SECRET env var is set first.
    from backend.app import app

    return TestClient(app)


# ----------------------------------------------------------------------
# /api/onboarding/web — gating
# ----------------------------------------------------------------------

def test_onboarding_web_rejects_no_session(app_client):
    """No cookie at all → 401."""
    response = app_client.post("/api/onboarding/web", json={"message": "hola"})
    assert response.status_code == 401


def test_onboarding_web_rejects_active_session(app_client):
    """Active (post-onboarding) session is not pending → 403."""
    response = app_client.post(
        "/api/onboarding/web",
        json={"message": "hola"},
        cookies=_active_cookie(),
    )
    assert response.status_code == 403


# ----------------------------------------------------------------------
# /api/onboarding/web — HTTP contract
#
# M2 originally mounted a keyword-stub here. M3.3 replaced the body with
# the Gemini turn dispatcher. The reply text is now LLM-generated and
# non-deterministic, so these tests assert only the additive HTTP seam
# from ADR-002 ("HTTP seam, additive, backwards-compatible"): status 200
# for a pending session, and a `metadata` dict with the documented keys.
# Behavioral assertions about the dispatcher live in test_onboarding_dispatcher.py.
# ----------------------------------------------------------------------

def test_onboarding_web_pending_session_returns_200(app_client):
    """Any message from a pending session must return 200 with the additive
    metadata shape, regardless of whether Gemini is reachable.

    If the LLM is unavailable, M3.3 returns 200 with metadata.error =
    'llm_unavailable' and an empty tool_calls list — that is a clean
    failure, NOT a 5xx. The user-visible recovery copy renders client-side.
    """
    response = app_client.post(
        "/api/onboarding/web",
        json={"message": "hola"},
        cookies=_pending_cookie(),
    )
    assert response.status_code == 200
    body = response.json()
    assert "response" in body
    assert "metadata" in body
    md = body["metadata"]
    # ADR-002 documented metadata keys (additive; some may be absent on a
    # given turn, but the dict shape is fixed).
    assert "step" in md
    assert "complete" in md


def test_onboarding_web_response_shape_matches_seam(app_client):
    """The contract M3 must respect: response (str) + metadata.step + metadata.complete."""
    response = app_client.post(
        "/api/onboarding/web",
        json={"message": "configurar"},
        cookies=_pending_cookie(),
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"response", "metadata"}
    assert isinstance(body["response"], str)
    assert "step" in body["metadata"]
    assert "complete" in body["metadata"]


# ----------------------------------------------------------------------
# /onboarding — the spectacle page
# ----------------------------------------------------------------------

def test_onboarding_page_renders_for_pending_session(app_client):
    """A pending session can load the spectacle page."""
    response = app_client.get("/onboarding", cookies=_pending_cookie())
    assert response.status_code == 200
    body = response.text
    # The greeting copy is rendered inside an sr-only node so AT picks it up.
    assert "Soy Timonel" in body
    # The chip text is hardcoded for v1.
    assert "Configurar mi negocio" in body
    # The factory mounts in onboarding mode.
    assert "mode: 'onboarding'" in body or 'mode: "onboarding"' in body


def test_onboarding_page_rejects_no_session(app_client):
    """No cookie → 401 (require_pending_session wins)."""
    response = app_client.get("/onboarding", follow_redirects=False)
    assert response.status_code == 401


def test_onboarding_page_rejects_active_session(app_client):
    """An active (logged-in) user who hits /onboarding gets 403; their
    landing page is /tenants/{phone} or /admin, not the spectacle."""
    response = app_client.get(
        "/onboarding",
        cookies=_active_cookie(),
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_onboarding_page_does_not_extend_base_chrome(app_client):
    """The spectacle is full-screen by design (skill rule 7: no progress
    bar, no chrome). Verify the global nav/footer from base.html are absent."""
    response = app_client.get("/onboarding", cookies=_pending_cookie())
    assert response.status_code == 200
    body = response.text
    # base.html's nav has the brand link "Volver a tenants" partner copy and
    # a logout form action="/auth/logout"; the onboarding page must not.
    assert 'action="/auth/logout"' not in body
    # The cream canvas is the frame; base.html does not own it on this page.
    assert "Cerrar sesión" not in body
