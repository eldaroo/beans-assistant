"""Tests for portal auth: AuthService, dependencies, and route gating."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "unit-test-secret-do-not-use-in-prod")


# ----------------------------------------------------------------------
# AuthService
# ----------------------------------------------------------------------

class _FakeRepo:
    def __init__(self, users=None):
        self.users = users or {}
        self.last_login_calls = []

    def get_by_email(self, email):
        return self.users.get(email.lower())

    def update_last_login(self, user_id):
        self.last_login_calls.append(user_id)


def _make_service(users=None):
    from backend.services.auth_service import AuthService
    return AuthService(repo=_FakeRepo(users or {}))


def test_authorize_unknown_email_raises():
    from backend.services.auth_service import UserNotAuthorizedError
    service = _make_service()
    with pytest.raises(UserNotAuthorizedError):
        service.authorize_google_email("nobody@gmail.com")


def test_authorize_known_email_updates_last_login():
    user = {"id": 7, "google_email": "owner@gmail.com", "phone_number": "+5491100000001", "role": "owner"}
    repo = _FakeRepo({"owner@gmail.com": user})
    from backend.services.auth_service import AuthService
    service = AuthService(repo=repo)
    result = service.authorize_google_email("Owner@Gmail.com")
    assert result == user
    assert repo.last_login_calls == [7]


def test_session_roundtrip():
    user = {"id": 7, "google_email": "owner@gmail.com", "phone_number": "+5491100000001", "role": "owner"}
    service = _make_service()
    token = service.issue_session(user)
    payload = service.verify_session(token)
    assert payload["user_id"] == 7
    assert payload["email"] == "owner@gmail.com"
    assert payload["phone_number"] == "+5491100000001"
    assert payload["role"] == "owner"


def test_session_rejects_garbage():
    service = _make_service()
    assert service.verify_session("not-a-real-token") is None
    assert service.verify_session("") is None


def test_session_rejects_other_secret(monkeypatch):
    user = {"id": 1, "google_email": "x@x.com", "phone_number": "+1", "role": "owner"}
    service = _make_service()
    token = service.issue_session(user)

    monkeypatch.setenv("SESSION_SECRET", "different-secret")
    other_service = _make_service()
    assert other_service.verify_session(token) is None


def test_missing_secret_raises(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    from backend.services.auth_service import AuthService
    with pytest.raises(RuntimeError):
        AuthService(repo=_FakeRepo())


# ----------------------------------------------------------------------
# Dependencies
# ----------------------------------------------------------------------

def _app_with_deps():
    from backend.auth.dependencies import require_auth, require_role, require_tenant_match
    app = FastAPI()

    @app.get("/protected")
    def protected(user: dict = Depends(require_auth)):
        return {"email": user["email"]}

    @app.get("/admin-only")
    def admin_only(user: dict = Depends(require_role("admin"))):
        return {"role": user["role"]}

    @app.get("/tenants/{phone}/data")
    def tenant_data(phone: str, _: dict = Depends(require_tenant_match)):
        return {"phone": phone}

    return app


def _login_cookie(role="owner", phone="+5491100000001", email="owner@gmail.com"):
    from backend.services.auth_service import SESSION_COOKIE_NAME, AuthService
    service = AuthService(repo=_FakeRepo())
    token = service.issue_session({"id": 1, "google_email": email, "phone_number": phone, "role": role})
    return {SESSION_COOKIE_NAME: token}


def test_protected_requires_auth():
    client = TestClient(_app_with_deps())
    r = client.get("/protected")
    assert r.status_code == 401


def test_protected_with_session_passes():
    client = TestClient(_app_with_deps())
    r = client.get("/protected", cookies=_login_cookie())
    assert r.status_code == 200
    assert r.json()["email"] == "owner@gmail.com"


def test_admin_only_blocks_owner():
    client = TestClient(_app_with_deps())
    r = client.get("/admin-only", cookies=_login_cookie(role="owner"))
    assert r.status_code == 403


def test_admin_only_allows_admin():
    client = TestClient(_app_with_deps())
    r = client.get("/admin-only", cookies=_login_cookie(role="admin"))
    assert r.status_code == 200


def test_tenant_match_blocks_cross_tenant():
    client = TestClient(_app_with_deps())
    cookies = _login_cookie(role="owner", phone="+5491100000001")
    r = client.get("/tenants/+5491100000002/data", cookies=cookies)
    assert r.status_code == 403


def test_tenant_match_allows_own_tenant():
    client = TestClient(_app_with_deps())
    cookies = _login_cookie(role="owner", phone="+5491100000001")
    r = client.get("/tenants/+5491100000001/data", cookies=cookies)
    assert r.status_code == 200


def test_tenant_match_admin_bypasses():
    client = TestClient(_app_with_deps())
    cookies = _login_cookie(role="admin", phone="+0")
    r = client.get("/tenants/+5491100000001/data", cookies=cookies)
    assert r.status_code == 200


def test_invalid_cookie_acts_as_no_session():
    from backend.services.auth_service import SESSION_COOKIE_NAME
    client = TestClient(_app_with_deps())
    r = client.get("/protected", cookies={SESSION_COOKIE_NAME: "garbage"})
    assert r.status_code == 401


# ----------------------------------------------------------------------
# Pending session (Onboarding M1)
# ----------------------------------------------------------------------

def _pending_cookie(email="newcomer@gmail.com", name="Newcomer"):
    from backend.services.auth_service import SESSION_COOKIE_NAME, AuthService
    svc = AuthService(repo=_FakeRepo())
    token = svc.issue_pending_session(email=email, name=name, picture="")
    return {SESSION_COOKIE_NAME: token}


def test_pending_session_roundtrip():
    svc = _make_service()
    token = svc.issue_pending_session(email="x@gmail.com", name="X", picture="http://p")
    payload = svc.verify_session(token)
    assert payload["kind"] == "pending"
    assert payload["email"] == "x@gmail.com"
    assert payload["name"] == "X"


def test_active_session_carries_kind_active():
    svc = _make_service()
    user = {"id": 1, "google_email": "o@e.com", "phone_number": "+1", "role": "owner"}
    payload = svc.verify_session(svc.issue_session(user))
    assert payload["kind"] == "active"


def test_require_auth_rejects_pending():
    from fastapi import Depends, FastAPI
    from backend.auth.dependencies import require_auth

    app = FastAPI()

    @app.get("/protected")
    def hit(_user: dict = Depends(require_auth)):
        return {"ok": True}

    client = TestClient(app)
    r = client.get("/protected", cookies=_pending_cookie())
    assert r.status_code == 403


def test_require_pending_session_accepts_pending():
    from fastapi import Depends, FastAPI
    from backend.auth.dependencies import require_pending_session

    app = FastAPI()

    @app.get("/onboarding")
    def hit(p: dict = Depends(require_pending_session)):
        return {"email": p["email"]}

    client = TestClient(app)
    r = client.get("/onboarding", cookies=_pending_cookie(email="abc@gmail.com"))
    assert r.status_code == 200
    assert r.json()["email"] == "abc@gmail.com"


def test_require_pending_session_rejects_active():
    from fastapi import Depends, FastAPI
    from backend.auth.dependencies import require_pending_session

    app = FastAPI()

    @app.get("/onboarding")
    def hit(p: dict = Depends(require_pending_session)):
        return {"email": p["email"]}

    client = TestClient(app)
    r = client.get("/onboarding", cookies=_login_cookie(role="owner"))
    assert r.status_code == 403


def test_require_pending_session_rejects_no_cookie():
    from fastapi import Depends, FastAPI
    from backend.auth.dependencies import require_pending_session

    app = FastAPI()

    @app.get("/onboarding")
    def hit(p: dict = Depends(require_pending_session)):
        return {"ok": True}

    client = TestClient(app)
    r = client.get("/onboarding")
    assert r.status_code == 401


def test_require_tenant_match_rejects_pending():
    from fastapi import Depends, FastAPI
    from backend.auth.dependencies import require_tenant_match

    app = FastAPI()

    @app.get("/tenants/{phone}/data")
    def hit(phone: str, _u: dict = Depends(require_tenant_match)):
        return {"phone": phone}

    client = TestClient(app)
    r = client.get("/tenants/+5491100000001/data", cookies=_pending_cookie())
    assert r.status_code == 403
