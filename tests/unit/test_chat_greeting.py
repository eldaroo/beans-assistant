"""Tests for the empty-state proactive greeting endpoint.

GET /api/tenants/{phone}/chat/greeting returns a non-null greeting when
the tenant's catalog is empty, null otherwise. The frontend gates by
localStorage so the user only sees this once per browser; the backend
only reports the current state.
"""
import pytest
from unittest.mock import patch
from contextlib import contextmanager

from fastapi.testclient import TestClient


@contextmanager
def _tenant_context_noop(phone):
    yield


def _client_with_auth_bypass():
    """The chat_tenant router is gated by require_tenant_match. For
    these tests we override that dependency to a no-op so we exercise
    the greeting endpoint logic in isolation."""
    from backend.app import app
    from backend.auth.dependencies import require_tenant_match

    app.dependency_overrides[require_tenant_match] = lambda: {"phone": "test", "is_admin": False}
    try:
        return app, TestClient(app)
    finally:
        pass


def _restore(app):
    app.dependency_overrides.clear()


@pytest.mark.unit
class TestChatGreetingEndpoint:
    def test_empty_catalog_returns_greeting(self):
        app, client = _client_with_auth_bypass()
        try:
            with patch("backend.api.chat_tenant.fetch_one", return_value={"has_products": False}), \
                 patch("backend.api.chat_tenant.tenant_context", _tenant_context_noop), \
                 patch("backend.api.chat_tenant.TenantManager") as mock_tm:
                mock_tm.return_value.normalize_phone_number.side_effect = lambda p: p
                mock_tm.return_value.resolve_tenant_phone.side_effect = lambda p: p
                resp = client.get("/api/tenants/+5491153695627/chat/greeting")

            assert resp.status_code == 200
            body = resp.json()
            assert body["greeting"] is not None
            assert "vacio" in body["greeting"].lower()
            assert body["kind"] == "empty_catalog"
        finally:
            _restore(app)

    def test_populated_catalog_returns_null_greeting(self):
        app, client = _client_with_auth_bypass()
        try:
            with patch("backend.api.chat_tenant.fetch_one", return_value={"has_products": True}), \
                 patch("backend.api.chat_tenant.tenant_context", _tenant_context_noop), \
                 patch("backend.api.chat_tenant.TenantManager") as mock_tm:
                mock_tm.return_value.normalize_phone_number.side_effect = lambda p: p
                mock_tm.return_value.resolve_tenant_phone.side_effect = lambda p: p
                resp = client.get("/api/tenants/+5491153695627/chat/greeting")

            assert resp.status_code == 200
            body = resp.json()
            assert body["greeting"] is None
        finally:
            _restore(app)

    def test_unknown_tenant_returns_404(self):
        app, client = _client_with_auth_bypass()
        try:
            with patch("backend.api.chat_tenant.TenantManager") as mock_tm:
                mock_tm.return_value.normalize_phone_number.side_effect = lambda p: p
                mock_tm.return_value.resolve_tenant_phone.return_value = None
                resp = client.get("/api/tenants/+1234/chat/greeting")

            assert resp.status_code == 404
        finally:
            _restore(app)
