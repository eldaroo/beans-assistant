"""Fixtures for browser-driven E2E tests.

These tests are the close-phase gate per `brain/agents/forge.md`: any phase
that ships UI interactivity (Alpine, custom events, hand-offs) must close
with `pytest -m browser` green. Asserting `console.error == 0` is the bar.

Pre-conditions to run:
- Backend running on http://127.0.0.1:8000.
- Postgres on 5433 with `tenants` + `app_users` + (eventually) pending sessions tables.
- Env vars: SESSION_SECRET (read from .env), USE_POSTGRES=true on the backend.

If the server is not reachable, every test in this directory is skipped with
a clear reason. We do not start the server from inside the suite — the
ritual is "leave the server running, then run the suite", same as a dev
would do manually before close.
"""

import os
import socket
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _server_reachable(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def _require_server():
    """Skip every browser test if the backend is not running on :8000."""
    if not _server_reachable("127.0.0.1", 8000):
        pytest.skip(
            "Backend not running on http://127.0.0.1:8000 — "
            "browser tests need the live server. Start it with: "
            "USE_POSTGRES=true POSTGRES_PORT=5433 python -m uvicorn backend.app:app --port 8000",
            allow_module_level=True,
        )


@pytest.fixture(scope="session")
def session_secret() -> str:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        pytest.skip("No .env file at project root; cannot forge sessions for browser tests.", allow_module_level=True)
    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("SESSION_SECRET="):
                return line.split("=", 1)[1].strip()
    pytest.skip("SESSION_SECRET not set in .env; cannot forge sessions.", allow_module_level=True)


@pytest.fixture(scope="session")
def auth_service(session_secret: str):
    """Return an AuthService bound to the same secret the server uses, so
    forged cookies validate."""
    os.environ["SESSION_SECRET"] = session_secret
    from backend.services.auth_service import AuthService

    class _NoopRepo:
        def get_by_email(self, e):
            return None

        def update_last_login(self, i):
            pass

    return AuthService(repo=_NoopRepo())


@pytest.fixture
def pending_cookie(auth_service, request):
    """Forge a `pending` session cookie for an arbitrary email.

    Override the email by passing `request.param = {'email': 'x@y.com', 'name': 'X'}`
    via parametrize, otherwise defaults to a synthetic newcomer.
    """
    from backend.services.auth_service import SESSION_COOKIE_NAME

    params = getattr(request, "param", {}) or {}
    email = params.get("email", "newcomer@gmail.com")
    name = params.get("name", "Newcomer")
    picture = params.get("picture", "")
    token = auth_service.issue_pending_session(email=email, name=name, picture=picture)
    return {"name": SESSION_COOKIE_NAME, "value": token, "url": "http://127.0.0.1:8000"}


@pytest.fixture
def active_owner_cookie(auth_service):
    from backend.services.auth_service import SESSION_COOKIE_NAME

    token = auth_service.issue_session(
        {"id": 1, "google_email": "owner@bitacora.test", "phone_number": "+5491100000001", "role": "owner"}
    )
    return {"name": SESSION_COOKIE_NAME, "value": token, "url": "http://127.0.0.1:8000"}


@pytest.fixture
def active_admin_cookie(auth_service):
    from backend.services.auth_service import SESSION_COOKIE_NAME

    token = auth_service.issue_session(
        {"id": 2, "google_email": "admin@bitacora.test", "phone_number": "+0", "role": "admin"}
    )
    return {"name": SESSION_COOKIE_NAME, "value": token, "url": "http://127.0.0.1:8000"}


@pytest.fixture
def browser():
    """Headless Chromium for one test."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


@pytest.fixture
def page_with_cookies(browser):
    """Factory: `page = page_with_cookies([cookie_dict, ...])`.

    Returns a tuple `(page, errors)`. `errors` is a live list that the
    test can assert is empty at the end (zero `console.error`,
    zero `pageerror`). Cosmetic warnings (Tailwind CDN nag) are filtered.
    """
    pages = []

    def _factory(cookies):
        ctx = browser.new_context()
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        errors: list[str] = []

        def _on_console(msg):
            if msg.type != "error":
                return
            text = msg.text or ""
            if "tailwindcss" in text.lower() and "production" in text.lower():
                return  # CDN nag, cosmetic
            errors.append(f"console.error: {text}")

        def _on_pageerror(exc):
            errors.append(f"pageerror: {exc.message}")

        page.on("console", _on_console)
        page.on("pageerror", _on_pageerror)
        pages.append((page, ctx, errors))
        return page, errors

    yield _factory

    for _page, ctx, _errors in pages:
        ctx.close()
