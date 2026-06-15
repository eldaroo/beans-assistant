"""
A logged-out browser opening a gated PAGE must be redirected to /login, not
shown the raw {"detail": "Authentication required"} JSON. API and XHR callers
keep the JSON 401 so the frontend's own fetch error handling is unchanged.

See the auth_aware_http_exception_handler in backend/app.py.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.app import app
    return TestClient(app)


@pytest.mark.unit
class TestAuthRedirect:
    def test_page_navigation_unauth_redirects_to_login(self, client):
        # Browser navigation (HTML accept), no session cookie.
        r = client.get(
            "/tenants/+54955885565",
            headers={"accept": "text/html,application/xhtml+xml"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"] == "/login"

    def test_api_call_unauth_stays_json(self, client):
        # /api/ path must keep the JSON 401 even with an HTML accept header,
        # so the frontend's fetch error handling is unchanged.
        r = client.get(
            "/api/tenants/+54955885565/products",
            headers={"accept": "text/html"},
            follow_redirects=False,
        )
        assert r.status_code == 401
        assert r.json()["detail"]

    def test_xhr_to_page_unauth_stays_json(self, client):
        # A non-HTML accept (XHR/fetch) to a page route is not a navigation;
        # keep the JSON so we never redirect a programmatic caller.
        r = client.get(
            "/tenants/+54955885565",
            headers={"accept": "application/json"},
            follow_redirects=False,
        )
        assert r.status_code == 401
