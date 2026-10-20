"""Internal operation API contract (spec 007 M1, D-036/D-037).

These prove the seam the native-tool-use chat depends on, with the stock read and
tenant_context mocked (the real DB read is covered by the stock tests): the endpoint
is internal-token only, the tenant is taken ONLY from the pinned header and never
from the body, and every response uses the named envelope.
"""
import contextlib

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient

TOKEN = "test-internal-token-007"
PHONE = "+5491100000001"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-internal-ops")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)

    from backend.api import internal_ops

    # Record what phone the service is scoped to; return a fixed stock payload.
    calls = {}

    def fake_get_current_stock(phone, limit, offset):
        calls["phone"] = phone
        return [{"product_id": 1, "sku": "PCC-001", "name": "Pulsera Cafe Clasica", "quantity": 48}]

    @contextlib.contextmanager
    def fake_tenant_scope(phone):
        calls["scoped_phone"] = phone
        yield

    monkeypatch.setattr(internal_ops.stock_service, "get_current_stock", fake_get_current_stock)
    monkeypatch.setattr(internal_ops, "tenant_scope", fake_tenant_scope)

    from backend.app import app

    c = TestClient(app)
    c._calls = calls
    return c


def test_read_stock_rejects_without_internal_token(client):
    r = client.post("/internal/ops/read_stock", headers={"x-beans-tenant": PHONE})
    assert r.status_code == 401
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "unauthorized"


def test_read_stock_requires_a_pinned_tenant(client):
    r = client.post("/internal/ops/read_stock", headers={"x-internal-token": TOKEN})
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "tenant_unpinned"


def test_read_stock_returns_stock_for_the_pinned_tenant(client):
    r = client.post(
        "/internal/ops/read_stock",
        headers={"x-internal-token": TOKEN, "x-beans-tenant": PHONE},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["stock"][0]["sku"] == "PCC-001"
    # The read ran under the pinned tenant.
    assert client._calls["phone"] == PHONE
    assert client._calls["scoped_phone"] == PHONE


def test_body_phone_is_ignored_tenant_comes_only_from_the_pinned_header(client):
    # A hostile/confused caller puts a different phone in the body. It changes nothing:
    # scope is the header (D-037), so the service is still called with the pinned phone.
    r = client.post(
        "/internal/ops/read_stock",
        headers={"x-internal-token": TOKEN, "x-beans-tenant": PHONE},
        json={"phone": "+99999999999", "tenant": "+99999999999"},
    )
    assert r.status_code == 200
    assert client._calls["phone"] == PHONE
    assert client._calls["scoped_phone"] == PHONE
