"""Productos ABM page tests (spec 004, S2, T-006).

Two layers. The template render asserts the page is built on cc_base (one owner
brand, held rail, Timonel, active rail item) and carries the Alpine
productosDashboard factory with the reused endpoints, the add/edit modal (SKU +
Nombre + Costo + Precio), and the dollars<->cents money conversion in one place.
The route test drives GET /productos/{phone} through the real app with the
internal-token bypass and a stubbed service, proving it returns 200, lists the
tenant's products in the seed, and is no-store + owner-gated (AC3).
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader

from backend.modules import nav

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"


def _product(**kw):
    base = dict(id=1, sku="BC-PROD-CAFE-500", name="Café molido 500g",
                description="Tostado medio", unit_cost_cents=210,
                unit_price_cents=650, is_active=True)
    base.update(kw)
    return SimpleNamespace(**base)


def _render(products):
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)
    rows = [
        {"id": p.id, "sku": p.sku, "name": p.name, "description": p.description or "",
         "unit_cost_cents": p.unit_cost_cents, "unit_price_cents": p.unit_price_cents,
         "is_active": bool(p.is_active)}
        for p in products
    ]
    return env.get_template("productos.html").render(
        phone="+100", view={"products": rows}, business_name="Beans&Co",
        nav=nav.owner_rail("+100"),
        tabs=nav.owner_tabs(), active_tab=nav.tab_id_for_module("productos"),
        active_route="productos",
    )


def test_extends_base_and_drops_own_doctype():
    src = (_TEMPLATES / "productos.html").read_text(encoding="utf-8")
    assert '{% extends "cc_base.html" %}' in src
    assert "<!doctype html>" not in src


def test_renders_shell_tabs_timonel_and_active_tab():
    import re
    html = _render([_product()])
    assert 'class="cc-tabs"' in html and 'id="themebtn"' in html
    assert 'beansChat({ phone: "+100"' in html and 'class="tim-launch"' in html
    # spec 006 T-005: this page sits under its group tab (Operación), selected
    m = re.search(r'<a[^>]*data-cc-tab="operacion"[^>]*>', html)
    assert m and 'aria-selected="true"' in m.group(0)


def test_seeds_products_and_carries_the_crud_factory():
    html = _render([_product(name="Café molido 500g"), _product(id=2, sku="BC-VERDES", name="verdes")])
    # the initial active products are seeded into the page (AC3: GET lists them)
    assert "Café molido 500g" in html and "verdes" in html
    # the one Alpine factory over the reused endpoints, no second write path
    assert "productosDashboard({ phone:" in html
    assert '"/api/tenants/" + encodeURIComponent(opts.phone) + "/products"' in html
    # create (POST) / edit (PUT) / soft-delete (DELETE), each refetching
    assert '"PUT"' in html and '"POST"' in html and "method: method" in html
    assert 'method: "DELETE"' in html and "await this.refetch()" in html


def test_blank_price_is_null_never_a_fabricated_zero():
    """Honesty (council Edut, Marcus): a blank cost/price is null, never 0, and
    CREATE rejects a blank instead of writing a product as free/zero-cost."""
    html = _render([_product()])
    # inputToCents yields null for a blank/invalid field (not 0)
    assert "return null;" in html
    # CREATE requires both cost and price (reject blank, never fabricate 0)
    assert "costCents === null" in html and "priceCents === null" in html


def test_modal_has_sku_name_costo_precio_and_money_is_one_place():
    html = _render([_product()])
    for label in (">SKU<", ">Nombre<", ">Costo<", ">Precio<"):
        assert label in html, label
    # the money trap handled once: dollars in the form, cents on the wire
    assert "Math.round(n * 100)" in html          # inputToCents
    assert "(cents / 100).toFixed(2)" in html      # money + centsToInput
    assert '"Sin precio"' in html                  # null price is honest, not $0


def test_seed_island_is_single_quoted_and_escapes_hostile_strings():
    """council Tamir BLOCKER regression: the x-data island must be SINGLE-quoted
    and a hostile product name/sku must not break out of the attribute or open a
    tag. tojson escapes ' -> \\u0027 and < -> \\u003c inside the single-quoted attr."""
    hostile = _product(
        id=9, sku="X'\"</script><img src=x onerror=alert(1)>", name="ev'il\"name"
    )
    html = _render([hostile])
    assert "x-data='productosDashboard" in html          # single-quoted attribute
    assert "</script><img" not in html                    # no raw tag breakout
    assert "\\u0027" in html and "\\u003c" in html         # ' and < escaped in the island
    assert ' x-data="productosDashboard' not in html       # never the broken double-quote form


def test_empty_state_invites_the_first_product():
    html = _render([])
    assert "Todavía no cargaste productos" in html
    assert "Agregar el primero" in html


# --------------------------------------------------------------------------
# Route layer: GET /productos/{phone} serves on the real app (AC3).
# --------------------------------------------------------------------------
TOKEN = "test-internal-token"


@pytest.fixture
def client(monkeypatch):
    pytest.importorskip("httpx")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    from backend.app import app
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def stub_products(monkeypatch):
    from contextlib import contextmanager
    from backend.api import productos as productos_api

    @contextmanager
    def _noop(_phone):
        yield

    monkeypatch.setattr(productos_api, "tenant_scope", _noop)
    monkeypatch.setattr(productos_api.nav, "business_name", lambda phone: "Beans&Co")
    monkeypatch.setattr(
        productos_api._service, "list_products",
        lambda phone, include_inactive=False, limit=200, offset=0: [
            _product(id=1, name="Café molido 500g", sku="BC-CAFE-500"),
            _product(id=2, name="verdes", sku="BC-VERDES", unit_price_cents=None),
        ],
    )


def test_route_returns_200_and_lists_products(client, stub_products):
    resp = client.get("/productos/+100", headers={"x-internal-token": TOKEN})
    assert resp.status_code == 200
    body = resp.text
    assert "Café molido 500g" in body and "verdes" in body
    assert "productosDashboard" in body
    assert resp.headers.get("cache-control", "").startswith("no-store")


def test_route_requires_auth(client):
    resp = client.get("/productos/+100", follow_redirects=False)
    assert resp.status_code in (302, 401, 403)


def test_route_is_registered():
    from backend.app import app
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/productos/{phone}" in paths
