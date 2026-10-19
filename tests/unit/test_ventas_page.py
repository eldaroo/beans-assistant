"""Ventas page tests (spec 004, S4, T-008 + T-009).

Template render + route + the tile repoint. Asserts the page lists sales, cancels
via DELETE, opens a detail modal from GET /sales/{id} (not an alert), and records
a sale through a line-item POST /sales (built, not ported). The x-data island is
single-quoted and escapes hostile strings (council Tamir). The Ventas tile is
repointed off the legacy ?tab=sales bounce to /ventas/{phone} (AC5).
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader

from backend.modules import nav, registry
from backend.modules.providers import ventas_module

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"


def _item(**kw):
    base = dict(product_name="Café molido 500g", product_sku="BC-CAFE-500",
                quantity=2, unit_price_cents=650, line_total_cents=1300)
    base.update(kw)
    return SimpleNamespace(**base)


def _sale(**kw):
    base = dict(id=1, sale_number="V-0001", status="PAID", total_amount_cents=1300,
                customer_name="Ana", created_at="2026-10-15T10:00:00", items=[_item()])
    base.update(kw)
    return SimpleNamespace(**base)


def _product(**kw):
    base = dict(id=1, name="Café molido 500g", sku="BC-CAFE-500", unit_price_cents=650)
    base.update(kw)
    return SimpleNamespace(**base)


def _rows(sales, products):
    from backend.api import ventas as v
    return {"sales": [v._sale_row(s) for s in sales], "products": [v._product_row(p) for p in products]}


def _render(sales, products):
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)
    return env.get_template("ventas.html").render(
        phone="+100", view=_rows(sales, products), business_name="Beans&Co",
        nav=nav.owner_rail("+100"),
        tabs=nav.owner_tabs(), active_tab=nav.tab_id_for_module("ventas"),
        active_route="ventas",
    )


def test_extends_base_and_drops_own_doctype():
    src = (_TEMPLATES / "ventas.html").read_text(encoding="utf-8")
    assert '{% extends "cc_base.html" %}' in src
    assert "<!doctype html>" not in src


def test_renders_shell_and_active_tab_on_absolute_route():
    import re
    html = _render([_sale()], [_product()])
    assert 'class="cc-tabs"' in html and 'id="themebtn"' in html and 'class="tim-launcher"' in html
    # spec 006 T-005: Ventas sits under the Operación tab, selected
    m = re.search(r'<a[^>]*data-cc-tab="operacion"[^>]*>', html)
    assert m and 'aria-selected="true"' in m.group(0)


def test_seeds_sales_and_carries_all_four_operations():
    html = _render([_sale(sale_number="V-0001"), _sale(id=2, sale_number="V-0002")], [_product()])
    assert "V-0001" in html and "V-0002" in html
    assert "ventasDashboard({ phone:" in html
    assert '"/api/tenants/" + encodeURIComponent(opts.phone) + "/sales"' in html
    # list (refetch), cancel (DELETE), detail (GET /sales/{id}), record-sale (POST)
    assert "await this.refetch()" in html
    assert 'method: "DELETE"' in html
    assert 'base + "/" + s.id' in html            # detail + cancel address a specific sale
    assert 'method: "POST"' in html and "items: items" in html


def test_record_sale_builds_line_items_against_the_real_contract():
    html = _render([_sale()], [_product()])
    # SaleCreate: status + customer_name + items[{product_id, quantity}]
    assert "product_id: ln.product_id" in html and "quantity: Number(ln.quantity)" in html
    assert "this.create.status" in html
    # at least one valid line is required, not a silent empty sale
    assert "Agregá al menos un ítem" in html


def test_detail_modal_reads_the_sale_endpoint_not_an_alert():
    html = _render([_sale()], [_product()])
    assert "openDetail" in html and "detail.sale" in html
    assert "alert(" not in html


def test_single_quoted_island_escapes_hostile_strings():
    html = _render([_sale(customer_name="ev'il\"</script><img src=x onerror=alert(1)>")], [_product()])
    assert "x-data='ventasDashboard" in html
    assert "</script><img" not in html
    assert "\\u0027" in html and "\\u003c" in html
    assert ' x-data="ventasDashboard' not in html


def test_empty_state_invites_the_first_sale():
    html = _render([], [_product()])
    assert "Todavía no registraste ventas" in html


def test_ventas_tile_repointed_off_legacy():
    mods = {m.id: m for m in registry.all_modules()}
    assert mods["ventas"].route == "/ventas/{phone}"
    assert ventas_module._ROUTE == "/ventas/{phone}"


# --- route layer ---
TOKEN = "test-internal-token"


@pytest.fixture
def client(monkeypatch):
    pytest.importorskip("httpx")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    from backend.app import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def stub(monkeypatch):
    from contextlib import contextmanager
    from backend.api import ventas as v

    @contextmanager
    def _noop(_phone):
        yield

    monkeypatch.setattr(v, "tenant_scope", _noop)
    monkeypatch.setattr(v.nav, "business_name", lambda phone: "Beans&Co")
    monkeypatch.setattr(v._sales, "list_sales", lambda phone, limit=50, offset=0: [_sale(sale_number="V-0001"), _sale(id=2, sale_number="V-0002")])
    monkeypatch.setattr(v._products, "list_products", lambda phone, include_inactive=False, limit=200, offset=0: [_product()])


def test_route_returns_200_and_lists_sales(client, stub):
    resp = client.get("/ventas/+100", headers={"x-internal-token": TOKEN})
    assert resp.status_code == 200
    assert "V-0001" in resp.text and "ventasDashboard" in resp.text
    assert resp.headers.get("cache-control", "").startswith("no-store")


def test_route_requires_auth(client):
    resp = client.get("/ventas/+100", follow_redirects=False)
    assert resp.status_code in (302, 401, 403)


def test_route_is_registered():
    from backend.app import app
    assert "/ventas/{phone}" in {getattr(r, "path", None) for r in app.routes}
