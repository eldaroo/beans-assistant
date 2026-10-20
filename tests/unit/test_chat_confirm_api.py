"""The /chat/confirm + /chat/undo endpoints (spec 007 M3, AC7 / AC15 / AC16).

Exercises the real route code against the isolated SQLite test DB, with the session gate and
tenant_context stubbed (the gate itself is unit-tested elsewhere; here we prove the commit is
idempotent, pessimistic, and reversible). The internal-token path is deliberately NOT used:
these endpoints are session-only, which is the point.
"""
import contextlib

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient

PHONE = "+5491100000001"
PREFIX = f"/api/tenants/{PHONE}/chat"


@pytest.fixture
def client(populated_db, monkeypatch):
    # A real owner session cookie so BOTH the router-level require_tenant_match and the
    # in-route require_tenant_session (session-only, AC7) pass — the honest auth path.
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-confirm")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "unused-here")

    from backend.services.auth_service import AuthService, SESSION_COOKIE_NAME

    class _NoopRepo:
        def get_by_email(self, e):
            return None

        def update_last_login(self, i):
            pass

    token = AuthService(repo=_NoopRepo()).issue_session(
        {"id": 1, "google_email": "owner@beans.test", "phone_number": PHONE, "role": "owner"}
    )

    from backend.api import chat_tenant

    # Only tenant RESOLUTION and cache are stubbed (no tenant registry / no Postgres here);
    # the DB is populated_db's patched SQLite. Auth is NOT stubbed — the forged cookie is real.
    monkeypatch.setattr(chat_tenant, "_resolve", lambda phone: phone)

    @contextlib.contextmanager
    def noop_ctx(phone):
        yield

    monkeypatch.setattr(chat_tenant, "tenant_context", noop_ctx)
    monkeypatch.setattr(chat_tenant.cache, "invalidate_all", lambda *a, **k: None)

    from backend.app import app

    c = TestClient(app)
    c.cookies.set(SESSION_COOKIE_NAME, token)
    return c


def _product_id(sku="BC-BRACELET-CLASSIC"):
    import database
    return database.fetch_one("SELECT id FROM products WHERE sku = ?", (sku,))["id"]


def _stage_sale(quantity, unit_price_cents=3500):
    import database
    from backend.repositories import pending_ops_repository as pending_ops
    pid = _product_id()
    token = f"op-{quantity}-{unit_price_cents}"
    pending_ops.stage(
        op_token=token, operation_type="REGISTER_SALE",
        args={"product_name": "Clásica", "quantity": quantity, "unit_price_cents": unit_price_cents,
              "line_total_cents": unit_price_cents * quantity, "reversible": True,
              "db_args": {"status": "PAID", "items": [
                  {"product_id": pid, "quantity": quantity, "unit_price_cents": unit_price_cents}]}},
        utterance="vendí", product_name="Clásica", candidate_count=1,
    )
    return token, pid


def test_confirm_commits_once_and_is_idempotent(client):
    import database
    token, pid = _stage_sale(quantity=2)
    database.add_stock({"product_id": pid, "quantity": 10})

    r1 = client.post(f"{PREFIX}/confirm", json={"op_token": token})
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["committed"] is True
    assert "receipt" in b1 and b1["receipt"]["balance_label"]
    # Exactly one PAID sale landed.
    n = database.fetch_one("SELECT COUNT(*) AS c FROM sales WHERE status = 'PAID'")["c"]
    assert n == 1

    # Idempotent double-submit: same receipt, no second sale.
    r2 = client.post(f"{PREFIX}/confirm", json={"op_token": token})
    b2 = r2.json()
    assert b2["committed"] is True and b2.get("idempotent") is True
    n2 = database.fetch_one("SELECT COUNT(*) AS c FROM sales WHERE status = 'PAID'")["c"]
    assert n2 == 1


def test_confirm_is_pessimistic_when_the_stock_guard_rejects(client):
    import database
    token, pid = _stage_sale(quantity=5)
    database.add_stock({"product_id": pid, "quantity": 1})  # not enough for 5

    r = client.post(f"{PREFIX}/confirm", json={"op_token": token})
    assert r.status_code == 200
    body = r.json()
    # No receipt, a clear reason, nothing committed (AC16).
    assert body["committed"] is False
    assert "receipt" not in body
    assert "stock" in body["message"].lower()
    n = database.fetch_one("SELECT COUNT(*) AS c FROM sales WHERE status = 'PAID'")["c"]
    assert n == 0


def test_undo_reverses_a_committed_sale_and_is_idempotent(client):
    import database
    token, pid = _stage_sale(quantity=2)
    database.add_stock({"product_id": pid, "quantity": 10})
    stock_before = database.fetch_one("SELECT stock_qty FROM stock_current WHERE product_id = ?", (pid,))["stock_qty"]

    client.post(f"{PREFIX}/confirm", json={"op_token": token})
    assert database.fetch_one("SELECT total_revenue_cents FROM revenue_paid")["total_revenue_cents"] == 7000

    u1 = client.post(f"{PREFIX}/undo", json={"op_token": token})
    assert u1.status_code == 200 and u1.json()["undone"] is True
    # Balance and stock restored to the cent; sale row preserved as CANCELLED.
    assert (database.fetch_one("SELECT total_revenue_cents FROM revenue_paid")["total_revenue_cents"] or 0) == 0
    assert database.fetch_one("SELECT stock_qty FROM stock_current WHERE product_id = ?", (pid,))["stock_qty"] == stock_before

    # Double Undo is a safe no-op.
    u2 = client.post(f"{PREFIX}/undo", json={"op_token": token})
    assert u2.json()["undone"] is True and u2.json().get("already") is True
    assert (database.fetch_one("SELECT total_revenue_cents FROM revenue_paid")["total_revenue_cents"] or 0) == 0


def test_confirm_unknown_op_is_a_named_error(client):
    r = client.post(f"{PREFIX}/confirm", json={"op_token": "does-not-exist"})
    assert r.status_code == 200
    assert r.json()["committed"] is False
    assert r.json()["error"]["code"] == "unknown_op"


# ── M4 confirm-only ops commit through the same single path, with no Undo (AC11) ────

def _stage(op_token, op_type, args, product_name=None):
    from backend.repositories import pending_ops_repository as pending_ops
    pending_ops.stage(op_token=op_token, operation_type=op_type, args=args,
                      utterance=None, product_name=product_name, candidate_count=1)


def test_update_product_price_commits_confirm_only_no_undo(client):
    import database
    pid = _product_id()
    _stage("op-price", "UPDATE_PRODUCT_PRICE",
           {"product_name": "Clásica", "unit_price_cents": 9900, "reversible": False,
            "irreversible": True, "db_args": {"product_id": pid, "unit_price_cents": 9900}},
           product_name="Clásica")
    r = client.post(f"{PREFIX}/confirm", json={"op_token": "op-price"})
    body = r.json()
    assert body["committed"] is True
    assert body["reversible"] is False  # no Undo toast for an irreversible op
    assert database.fetch_one("SELECT unit_price_cents FROM products WHERE id = ?", (pid,))["unit_price_cents"] == 9900


def test_register_product_commits_confirm_only(client):
    import database
    _stage("op-newprod", "REGISTER_PRODUCT",
           {"product_name": "Vela de soja", "reversible": False, "irreversible": True,
            "db_args": {"sku": "VELA-DE-SOJA", "name": "Vela de soja",
                        "unit_price_cents": 2500, "unit_cost_cents": 800}},
           product_name="Vela de soja")
    r = client.post(f"{PREFIX}/confirm", json={"op_token": "op-newprod"})
    assert r.json()["committed"] is True and r.json()["reversible"] is False
    assert database.fetch_one("SELECT 1 FROM products WHERE sku = 'VELA-DE-SOJA'") is not None


def test_deactivate_product_commits_confirm_only(client):
    import database
    pid = _product_id()
    _stage("op-deact", "DEACTIVATE_PRODUCT",
           {"product_name": "Clásica", "reversible": False, "irreversible": True,
            "db_args": {"product_id": pid}}, product_name="Clásica")
    r = client.post(f"{PREFIX}/confirm", json={"op_token": "op-deact"})
    assert r.json()["committed"] is True
    row = database.fetch_one("SELECT is_active FROM products WHERE id = ?", (pid,))
    assert not row["is_active"]
