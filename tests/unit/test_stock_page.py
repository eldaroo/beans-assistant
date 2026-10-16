"""Stock page tests (spec 004, S3, T-007).

Template render + route + the tile repoint. The signed-delta trap (the cell
shows the absolute quantity, POST /stock/adjust takes newQty-currentQty) is the
load-bearing assertion (Amelia). Also asserts the Stock tile and its low-stock
attention item are repointed off the legacy ?tab=stock bounce to /stock/{phone}
(AC4).
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader

from backend.modules import nav, registry
from backend.modules.providers import stock_module

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"


def _stock(**kw):
    base = dict(product_id=1, sku="BC-CAFE-500", name="Café molido 500g", stock_qty=5)
    base.update(kw)
    return SimpleNamespace(**base)


def _render(items, threshold=20):
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)
    rows = [{"product_id": s.product_id, "sku": s.sku, "name": s.name, "stock_qty": int(s.stock_qty)} for s in items]
    return env.get_template("stock.html").render(
        phone="+100", view={"stock": rows, "low_stock_threshold": threshold},
        business_name="Beans&Co", nav=nav.owner_rail("+100"), active_route="stock",
    )


def test_extends_base_and_drops_own_doctype():
    src = (_TEMPLATES / "stock.html").read_text(encoding="utf-8")
    assert '{% extends "cc_base.html" %}' in src
    assert "<!doctype html>" not in src


def test_renders_shell_and_active_stock_item_on_absolute_route():
    html = _render([_stock()])
    assert 'class="rail"' in html and 'id="themebtn"' in html
    assert 'class="tim-launch"' in html
    # the Stock rail item is current and links to the NEW page, not the legacy tab
    assert 'aria-current="true" href="/stock"' in html
    assert "?tab=stock" not in html


def test_seeds_stock_and_carries_the_factory_with_both_write_paths():
    html = _render([_stock(name="Termos Stanley"), _stock(product_id=2, name="verdes", stock_qty=40)])
    # ASCII names so the assertion is robust to tojson's unicode escaping of the seed
    assert "Termos Stanley" in html and "verdes" in html
    assert "stockDashboard({ phone:" in html
    assert '"/api/tenants/" + encodeURIComponent(opts.phone) + "/stock"' in html
    # add units via /stock/add, adjust via /stock/adjust — both exercised (AC4)
    assert 'base + "/add"' in html and 'base + "/adjust"' in html


def test_inline_adjust_sends_the_signed_delta_not_the_absolute():
    """The signed-delta trap: the endpoint receives newQty - currentQty."""
    html = _render([_stock()])
    assert "var delta = target - p.stock_qty;" in html
    assert "if (delta === 0) return;" in html           # no-op on no change
    assert '"quantity": delta' in html or "quantity: delta" in html


def test_low_stock_filter_and_badge_use_the_module_threshold():
    html = _render([_stock(stock_qty=3)], threshold=20)
    assert "Solo bajo stock" in html
    assert "isLow" in html and "p.stock_qty <= t" in html
    # the threshold flows from the module, not a magic number in the template
    assert "threshold: 20" in html


def test_add_stock_modal_has_product_quantity_and_reason():
    html = _render([_stock()])
    assert ">Producto<" in html and ">Unidades a agregar<" in html and ">Motivo<" in html


def test_seed_island_is_single_quoted_and_escapes_hostile_strings():
    """council Tamir regression (mirrors the productos test): the stock x-data
    island must be single-quoted and a hostile product name must not break out."""
    html = _render([_stock(name="ev'il\"name</script><img src=x onerror=alert(1)>")])
    assert "x-data='stockDashboard" in html
    assert "</script><img" not in html
    assert "\\u0027" in html and "\\u003c" in html
    assert ' x-data="stockDashboard' not in html


# --------------------------------------------------------------------------
# Registry repoint (AC4): the Stock tile and its attention item leave legacy.
# --------------------------------------------------------------------------
def test_stock_tile_repointed_to_its_own_page():
    mods = {m.id: m for m in registry.all_modules()}
    assert mods["stock"].route == "/stock/{phone}"


def test_stock_attention_drills_into_the_new_page_not_the_legacy_tab():
    # the low-stock attention item's route follows the module to /stock/{phone}
    assert stock_module._ROUTE == "/stock/{phone}"
    snap = stock_module.compute_snapshot([_stock(stock_qty=2)])
    assert snap.attention and all(a.route == "/stock/{phone}" for a in snap.attention)


# --------------------------------------------------------------------------
# Route layer: GET /stock/{phone} serves on the real app (AC4).
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
def stub_stock(monkeypatch):
    from contextlib import contextmanager
    from backend.api import stock_page as sp

    @contextmanager
    def _noop(_phone):
        yield

    monkeypatch.setattr(sp, "tenant_scope", _noop)
    monkeypatch.setattr(sp.nav, "business_name", lambda phone: "Beans&Co")
    monkeypatch.setattr(
        sp._service, "get_current_stock",
        lambda phone, limit=200, offset=0: [
            _stock(product_id=1, name="Termos Stanley", stock_qty=5),
            _stock(product_id=2, name="verdes", stock_qty=40),
        ],
    )


def test_route_returns_200_and_lists_stock(client, stub_stock):
    resp = client.get("/stock/+100", headers={"x-internal-token": TOKEN})
    assert resp.status_code == 200
    body = resp.text
    assert "Termos Stanley" in body and "verdes" in body
    assert "stockDashboard" in body
    assert resp.headers.get("cache-control", "").startswith("no-store")


def test_route_requires_auth(client):
    resp = client.get("/stock/+100", follow_redirects=False)
    assert resp.status_code in (302, 401, 403)


def test_route_is_registered():
    from backend.app import app
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/stock/{phone}" in paths
