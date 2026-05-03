"""Phase 2 scoping tests: gated routers reject cross-tenant API calls.

These run against an isolated FastAPI app that mounts only the dependency
under test, so we don't need a real DB. Echo bar: owner blocked from cross-tenant,
admin bypasses, no-cookie=401, internal token bypasses for service endpoints.
"""

from contextlib import contextmanager

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "scoping-test-secret")


def _login_cookie(role="owner", phone="+5491100000001", email="o@e.com"):
    from backend.services.auth_service import SESSION_COOKIE_NAME, AuthService

    class Repo:
        def get_by_email(self, e): return None
        def update_last_login(self, i): pass

    svc = AuthService(repo=Repo())
    token = svc.issue_session({"id": 1, "google_email": email, "phone_number": phone, "role": role})
    return {SESSION_COOKIE_NAME: token}


def _gated_app():
    """A minimal app that mounts each tenant-scoped router with require_tenant_match."""
    from backend.api import products as products_api
    from backend.auth.dependencies import require_tenant_match

    @contextmanager
    def _passthrough(_phone): yield

    products_api.tenant_scope = _passthrough  # bypass DB context
    products_api.products_service.list_products = lambda *a, **kw: []

    app = FastAPI()
    app.include_router(
        products_api.router,
        prefix="/api/tenants",
        dependencies=[Depends(require_tenant_match)],
    )
    return app


def test_owner_can_read_own_tenant_products(monkeypatch):
    app = _gated_app()
    client = TestClient(app)
    cookies = _login_cookie(phone="+5491100000001")
    r = client.get("/api/tenants/+5491100000001/products", cookies=cookies)
    assert r.status_code == 200, r.text


def test_owner_blocked_from_other_tenant_products():
    app = _gated_app()
    client = TestClient(app)
    cookies = _login_cookie(phone="+5491100000001")
    r = client.get("/api/tenants/+5491100000999/products", cookies=cookies)
    assert r.status_code == 403


def test_admin_bypasses_tenant_match():
    app = _gated_app()
    client = TestClient(app)
    cookies = _login_cookie(role="admin", phone="+0")
    r = client.get("/api/tenants/+5491100000999/products", cookies=cookies)
    assert r.status_code == 200


def test_no_cookie_returns_401():
    app = _gated_app()
    client = TestClient(app)
    r = client.get("/api/tenants/+5491100000001/products")
    assert r.status_code == 401


def test_invalid_cookie_returns_401():
    from backend.services.auth_service import SESSION_COOKIE_NAME
    app = _gated_app()
    client = TestClient(app)
    r = client.get(
        "/api/tenants/+5491100000001/products",
        cookies={SESSION_COOKIE_NAME: "garbage"},
    )
    assert r.status_code == 401


def test_internal_token_bypasses_tenant_match(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "test-internal-token")
    app = _gated_app()
    client = TestClient(app)
    r = client.get(
        "/api/tenants/+5491100000999/products",
        headers={"X-Internal-Token": "test-internal-token"},
    )
    assert r.status_code == 200


def test_internal_token_wrong_value_falls_through_to_session(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "right-token")
    app = _gated_app()
    client = TestClient(app)
    # No cookie + wrong token = 401
    r = client.get(
        "/api/tenants/+5491100000001/products",
        headers={"X-Internal-Token": "wrong-token"},
    )
    assert r.status_code == 401


def test_internal_token_unset_means_header_ignored(monkeypatch):
    monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
    app = _gated_app()
    client = TestClient(app)
    # Even if a token header is sent, with no env var configured, falls back to session.
    r = client.get(
        "/api/tenants/+5491100000999/products",
        headers={"X-Internal-Token": "anything"},
    )
    assert r.status_code == 401


def test_require_internal_or_admin_accepts_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "tok")
    from backend.auth.dependencies import require_internal_or_admin

    app = FastAPI()

    @app.get("/internal-route")
    def hit(_user: dict = Depends(require_internal_or_admin)):
        return {"ok": True}

    client = TestClient(app)
    r = client.get("/internal-route", headers={"X-Internal-Token": "tok"})
    assert r.status_code == 200


def test_require_internal_or_admin_rejects_owner(monkeypatch):
    from backend.auth.dependencies import require_internal_or_admin

    app = FastAPI()

    @app.get("/internal-route")
    def hit(_user: dict = Depends(require_internal_or_admin)):
        return {"ok": True}

    client = TestClient(app)
    cookies = _login_cookie(role="owner")
    r = client.get("/internal-route", cookies=cookies)
    assert r.status_code == 403


def test_require_internal_or_admin_accepts_admin():
    from backend.auth.dependencies import require_internal_or_admin

    app = FastAPI()

    @app.get("/internal-route")
    def hit(_user: dict = Depends(require_internal_or_admin)):
        return {"ok": True}

    client = TestClient(app)
    cookies = _login_cookie(role="admin")
    r = client.get("/internal-route", cookies=cookies)
    assert r.status_code == 200
