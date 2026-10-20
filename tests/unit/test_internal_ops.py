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


# ── M2 read surface (s-04): revenue, profit, sales summary, module, business_status ──

AUTH = {"x-internal-token": TOKEN, "x-beans-tenant": PHONE}


@pytest.mark.parametrize(
    "path",
    [
        "/internal/ops/read_revenue",
        "/internal/ops/read_profit",
        "/internal/ops/read_sales_summary",
        "/internal/ops/read_module",
        "/internal/ops/business_status",
    ],
)
def test_every_read_op_rejects_without_the_internal_token(client, path):
    r = client.post(path, headers={"x-beans-tenant": PHONE})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    "path",
    [
        "/internal/ops/read_revenue",
        "/internal/ops/read_profit",
        "/internal/ops/business_status",
    ],
)
def test_read_ops_require_a_pinned_tenant(client, path):
    r = client.post(path, headers={"x-internal-token": TOKEN})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "tenant_unpinned"


def test_read_revenue_returns_revenue_for_the_pinned_tenant(client, monkeypatch):
    from backend.api import internal_ops

    seen = {}

    def fake_revenue(phone):
        seen["phone"] = phone
        return {"total_revenue_cents": 40000, "revenue_usd": 400.0}

    monkeypatch.setattr(internal_ops.analytics_service, "get_revenue", fake_revenue)
    r = client.post("/internal/ops/read_revenue", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["revenue"]["revenue_usd"] == 400.0
    assert seen["phone"] == PHONE


def test_read_profit_returns_profit_for_the_pinned_tenant(client, monkeypatch):
    from backend.api import internal_ops

    monkeypatch.setattr(internal_ops.analytics_service, "get_profit", lambda phone: {"profit_usd": 123.45})
    r = client.post("/internal/ops/read_profit", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["profit"]["profit_usd"] == 123.45


def test_read_sales_summary_passes_a_revalidated_limit_and_ignores_a_body_tenant(client, monkeypatch):
    from backend.api import internal_ops

    seen = {}

    def fake_summary(phone, limit):
        seen["phone"] = phone
        seen["limit"] = limit
        return [{"day": "2026-10-20", "paid_sales_count": 2, "paid_revenue_cents": 8000, "paid_revenue_usd": 80.0}]

    monkeypatch.setattr(internal_ops.analytics_service, "get_sales_summary", fake_summary)
    r = client.post("/internal/ops/read_sales_summary", headers=AUTH, json={"limit": 7, "phone": "+99999999999"})
    assert r.status_code == 200
    assert r.json()["sales_summary"][0]["paid_revenue_usd"] == 80.0
    assert seen["phone"] == PHONE  # tenant from header, never the body
    assert seen["limit"] == 7


def test_read_sales_summary_rejects_an_out_of_range_limit(client):
    # Pydantic re-validation (AC4): limit is bounded 1..50.
    r = client.post("/internal/ops/read_sales_summary", headers=AUTH, json={"limit": 999})
    assert r.status_code == 422


def test_read_module_rejects_an_unknown_module(client):
    r = client.post("/internal/ops/read_module", headers=AUTH, json={"module": "not_a_module"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "unknown_module"


def test_read_module_returns_the_named_modules_snapshot(client, monkeypatch):
    from backend.api import internal_ops
    from backend.modules.protocol import AttentionItem, Headline, Module, ModuleSnapshot, Severity

    snap = ModuleSnapshot(
        headline=Headline(value="12 u", trend="sin faltantes", trend_tone="good"),
        attention=[AttentionItem(Severity.MID, "Stock bajo: x quedan 3 u", action_label="Reponer", route="/stock/{phone}")],
    )
    fake_mod = Module(id="stock", label="Stock", route="/stock/{phone}", snapshot=lambda phone: snap)
    monkeypatch.setattr(internal_ops.registry, "all_modules", lambda: [fake_mod])
    monkeypatch.setattr(internal_ops, "MODULE_IDS", {"stock"})
    r = client.post("/internal/ops/read_module", headers=AUTH, json={"module": "stock"})
    assert r.status_code == 200
    body = r.json()
    assert body["module"]["id"] == "stock"
    assert body["module"]["headline"]["value"] == "12 u"
    assert body["module"]["attention"][0]["severity"] == int(Severity.MID)
    assert body["module"]["attention"][0]["severity_label"] == "MID"


def test_business_status_is_byte_equal_to_the_single_attention_aggregation(client, monkeypatch):
    """AC6: business_status returns exactly attention_service.aggregate()+prioritize() —
    the same list the home renders — not a second opinion computed in the endpoint."""
    from backend.api import internal_ops
    from backend.modules import attention_service
    from backend.modules.protocol import AttentionItem, Severity

    # Raw per-module items, out of severity order and over the cap of 5, so the test
    # exercises both the sort and the cap of aggregate()/prioritize().
    raw = [
        ("stock", [AttentionItem(Severity.MID, "m1"), AttentionItem(Severity.HIGH, "h1")]),
        ("ventas", [AttentionItem(Severity.LOW, "l1"), AttentionItem(Severity.HIGH, "h2")]),
        ("costos", [AttentionItem(Severity.MID, "m2"), AttentionItem(Severity.LOW, "l2"), AttentionItem(Severity.HIGH, "h3")]),
    ]
    expected = attention_service.aggregate(raw)  # single source of truth

    class FakeView:
        attention = expected

    monkeypatch.setattr(internal_ops, "build_home", lambda phone: FakeView())
    r = client.post("/internal/ops/business_status", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # Byte-equal to the serialized aggregate()/prioritize() output, in its order, capped.
    assert body["attention"] == [internal_ops._attention_item(i) for i in expected]
    # And the cap held (3 HIGH + ... capped at 5).
    assert len(body["attention"]) <= attention_service.ATTENTION_CAP
