"""Single-business surface: phone-less owner URLs (2026-10-16).

Beans&Co is operated as ONE business, so the owner never sees a phone in the
URL. The multi-tenant kernel underneath is untouched; the phone-less paths
resolve the business from the session and rewrite internally to the existing
tenant-scoped page routes. These assert that contract end to end:

1. href_for renders an absolute module route phone-less ('/stock/{phone}' -> '/stock').
2. A phone-less page resolves the business from the SESSION and serves the real
   tenant-scoped page in place (200, no redirect to a phone-ful URL), with
   require_tenant_match running underneath exactly as before.
3. A phone-less page with no session bounces to /login (not a raw 404).
4. The root redirects an owner to the phone-less /home.
"""
from pathlib import Path

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader

from backend.api import home as home_api
from backend.modules import home_service
from backend.modules.home_service import HomeView, _rail_groups
from backend.modules.protocol import ModuleTile

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"
SECRET = "test-session-secret-single-business"
PHONE = "+100"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    from backend.app import app

    return TestClient(app)


def _owner_cookie():
    from backend.services.auth_service import AuthService, SESSION_COOKIE_NAME

    class _NoopRepo:
        def get_by_email(self, e):
            return None

        def update_last_login(self, i):
            pass

    token = AuthService(repo=_NoopRepo()).issue_session(
        {"id": 1, "google_email": "owner@beansco.test", "phone_number": PHONE, "role": "owner"}
    )
    return SESSION_COOKIE_NAME, token


def _one_tile_view():
    tile = ModuleTile("stock", "Stock", "/stock/{phone}", "505 u", "", "flat", "ok", "Operación")
    return HomeView(tiles=[tile], attention=[], rail_groups=_rail_groups([tile]))


# 1 --------------------------------------------------------------- href_for
def test_href_for_renders_absolute_route_phone_less():
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)
    tpl = env.from_string(
        "{% from '_cc_macros.html' import href_for %}{{ href_for('/stock/{phone}', '+100') }}"
    )
    assert tpl.render() == "/stock"


# 2 ------------------------------------------- phone-less page via the session
def test_phoneless_home_resolves_business_from_session(client, monkeypatch):
    monkeypatch.setattr(home_api, "_resolve_business_name", lambda phone: "Beans&Co")
    monkeypatch.setattr(home_service, "build_home", lambda phone: _one_tile_view())
    name, token = _owner_cookie()
    client.cookies.set(name, token)

    resp = client.get("/home", follow_redirects=False)
    assert resp.status_code == 200, resp.text[:200]  # served in place; URL stays /home
    assert "control center" in resp.text.lower()


# 3 ------------------------------------------- no session -> login, not a 404
def test_phoneless_page_without_session_bounces_to_login(client):
    resp = client.get("/productos", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


# 4 ---------------------------------------------------- root -> phone-less home
def test_root_redirects_owner_to_phoneless_home(client):
    name, token = _owner_cookie()
    client.cookies.set(name, token)

    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/home"
