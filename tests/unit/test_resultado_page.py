"""Resultado page tests (spec 004, S5, T-010).

Template render + route + the tile repoint and mislabel fix. The page shows
ingresos (paid revenue), gastos, and ganancia (ingresos menos gastos, one
consistent live definition), plus the expenses list with add (POST /expenses)
and delete. The Resultado tile is repointed off the legacy ?tab=expenses bounce
to /resultado/{phone} (AC6, the mislabel fix: "Resultado" no longer opens the
gastos tab).
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader

from backend.modules import nav, registry
from backend.modules.providers import caja_module

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"


def _expense(**kw):
    base = dict(id=1, expense_date="2026-10-10T00:00:00", category="SUPPLIES",
                description="Insumos café", amount_cents=5000)
    base.update(kw)
    return SimpleNamespace(**base)


def _view(ingresos_cents, expenses, truncated=False, ganancia_server_cents=0):
    from backend.api import resultado as r
    return {
        "ingresos_cents": ingresos_cents,
        "ganancia_server_cents": ganancia_server_cents,
        "expenses": [r._expense_row(e) for e in expenses],
        "truncated": truncated,
    }


def _render(ingresos_cents, expenses, truncated=False, ganancia_server_cents=0):
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)
    return env.get_template("resultado.html").render(
        phone="+100", view=_view(ingresos_cents, expenses, truncated, ganancia_server_cents),
        business_name="Beans&Co", nav=nav.owner_rail("+100"), active_route="caja",
    )


def test_extends_base_and_drops_own_doctype():
    src = (_TEMPLATES / "resultado.html").read_text(encoding="utf-8")
    assert '{% extends "cc_base.html" %}' in src
    assert "<!doctype html>" not in src


def test_renders_shell_and_active_resultado_item_on_absolute_route():
    html = _render(100000, [_expense()])
    assert 'class="rail"' in html and 'class="tim-launch"' in html
    # the Resultado (caja) rail item is current and links to the NEW page
    assert 'aria-current="true" href="/resultado/+100"' in html
    assert "?tab=expenses" not in html


def test_shows_three_figures_and_the_expenses_table():
    # ASCII descriptions so the assertion is robust to tojson's unicode escaping
    html = _render(100000, [_expense(description="Insumos cafe"), _expense(id=2, description="Envio nacional")])
    assert ">Ingresos<" in html and ">Gastos<" in html and ">Ganancia<" in html
    assert "Insumos cafe" in html and "Envio nacional" in html
    assert "resultadoDashboard({ phone:" in html


def test_ganancia_is_ingresos_minus_gastos_one_definition():
    html = _render(100000, [_expense()])
    assert "ingresosCents - this.gastosCents()" in html           # ganancia derived (not truncated)
    assert "reduce" in html                                        # gastos = sum of expenses
    assert '"/api/tenants/" + encodeURIComponent(opts.phone) + "/expenses"' in html


def test_truncated_uses_server_ganancia_so_it_matches_the_tile():
    """council Edut/Winston/Marcus BLOCKER: a truncated expense list must NOT
    understate gastos / overstate ganancia. The page seeds the server's profit
    and uses it as ganancia when truncated, so it agrees with the home caja tile."""
    html = _render(600000, [_expense()], truncated=True, ganancia_server_cents=99000)
    # the server figure is seeded into the island and used in the truncated branch
    assert "gananciaServerCents: 99000" in html
    assert "if (this.truncated) return this.gananciaServerCents;" in html
    assert "this.ingresosCents - this.gananciaServerCents" in html   # gastos back-derived
    # the list is marked partial so the owner knows it is not the full set
    assert "lista parcial" in html


def test_add_expense_validates_amount_and_description():
    html = _render(0, [])
    # ExpenseCreate requires amount_cents > 0 and a description
    assert "cents <= 0" in html and "!this.form.description.trim()" in html
    assert "amount_cents: cents" in html and "Math.round(n * 100)" in html


def test_single_quoted_island_escapes_hostile_strings():
    html = _render(100, [_expense(description="ev'il\"</script><img src=x onerror=alert(1)>")])
    assert "x-data='resultadoDashboard" in html
    assert "</script><img" not in html
    assert "\\u0027" in html and "\\u003c" in html


def test_caja_tile_repointed_and_mislabel_fixed():
    mods = {m.id: m for m in registry.all_modules()}
    assert mods["caja"].route == "/resultado/{phone}"       # not ?tab=expenses
    assert caja_module._ROUTE == "/resultado/{phone}"


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
    from backend.api import resultado as r

    @contextmanager
    def _noop(_phone):
        yield

    monkeypatch.setattr(r, "tenant_scope", _noop)
    monkeypatch.setattr(r.nav, "business_name", lambda phone: "Beans&Co")
    monkeypatch.setattr(r._analytics, "get_revenue", lambda phone: SimpleNamespace(revenue_usd=1000.0))
    monkeypatch.setattr(r._analytics, "get_profit", lambda phone: SimpleNamespace(profit_usd=950.0))
    monkeypatch.setattr(r._expenses, "list_expenses", lambda phone, limit=500, offset=0: [_expense(description="Insumos cafe")])


def test_route_returns_200_shows_figures_and_expenses(client, stub):
    resp = client.get("/resultado/+100", headers={"x-internal-token": TOKEN})
    assert resp.status_code == 200
    body = resp.text
    assert "Ingresos" in body and "Ganancia" in body and "Insumos cafe" in body
    assert "resultadoDashboard" in body
    assert resp.headers.get("cache-control", "").startswith("no-store")


def test_route_requires_auth(client):
    resp = client.get("/resultado/+100", follow_redirects=False)
    assert resp.status_code in (302, 401, 403)


def test_route_is_registered():
    from backend.app import app
    assert "/resultado/{phone}" in {getattr(r, "path", None) for r in app.routes}
