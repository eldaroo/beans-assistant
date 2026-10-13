"""Control Center route tests (M1): the new default landing actually serves.

Edut's deploy condition: the owner's new front door must be proven to return 200
and render the template on the pinned stack, not only at the viewmodel layer.
These drive GET /home/{phone} through the real FastAPI app (internal-token auth
bypass) with the tenant + viewmodel stubbed, so they exercise the route wiring,
the gating, and the Jinja render without a live Postgres.
"""
import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from backend.api import home as home_api
from backend.modules import home_service
from backend.modules.home_service import HomeView, _rail_groups
from backend.modules.protocol import AttentionItem, ModuleTile, Severity

TOKEN = "test-internal-token"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    from backend.app import app

    return TestClient(app)


def _fixed_view():
    tiles = [
        ModuleTile("caja", "Resultado", "?tab=expenses", "USD 1.4k", "acumulado", "good", "ok", "Operación"),
        ModuleTile("stock", "Stock", "?tab=stock", "505 u", "1 producto bajo", "warn", "ok", "Operación"),
        ModuleTile("ventas", "Ventas semana", "?tab=sales", "USD 1.9k", "3 ventas · 7 días", "good", "ok", "Operación"),
    ]
    att = [AttentionItem(Severity.HIGH, "Stock bajo: Pulsera quedan 5 u", "Reponer", "?tab=stock", "stock")]
    return HomeView(tiles=tiles, attention=att, rail_groups=_rail_groups(tiles))


def test_home_route_renders_200(client, monkeypatch):
    monkeypatch.setattr(home_api, "_resolve_business_name", lambda phone: "Beans&Co")
    monkeypatch.setattr(home_service, "build_home", lambda phone: _fixed_view())

    resp = client.get("/home/+100", headers={"x-internal-token": TOKEN})
    assert resp.status_code == 200
    body = resp.text
    assert "control center" in body.lower()
    assert "505 u" in body and "USD 1.4k" in body and "USD 1.9k" in body
    assert "Stock bajo: Pulsera quedan 5 u" in body
    # drill-down honours the module route (tab suffix on the dashboard)
    assert "/tenants/+100?tab=stock" in body
    assert resp.headers.get("cache-control", "").startswith("no-store")


def test_home_route_404_for_unknown_tenant(client, monkeypatch):
    from backend.services.tenants_service import TenantNotFoundError, TenantsService

    def _boom(self, phone):
        raise TenantNotFoundError(f"Tenant {phone} not found")

    monkeypatch.setattr(TenantsService, "get_tenant", _boom)
    resp = client.get("/home/+999", headers={"x-internal-token": TOKEN})
    assert resp.status_code == 404


def test_home_route_requires_auth(client):
    # No session, no internal token -> page nav bounces to /login (302).
    resp = client.get("/home/+100", follow_redirects=False)
    assert resp.status_code in (302, 401, 403)
