"""Control Center template render test (M1).

Renders control_center.html via a Jinja Environment (no web stack) with a
representative viewmodel, asserting the ported mockup's tokens, severity SHAPES,
tiles, degraded/empty states, and drill-down routes all render. Complements the
route test (full 200 on the app) and the viewmodel tests (build_home).
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.modules.home_service import HomeView, _rail_groups
from backend.modules.protocol import AttentionItem, ModuleTile, Severity

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"


def _env():
    return Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)


def _render(view, business_name="Beans&Co", phone="+100"):
    return _env().get_template("control_center.html").render(phone=phone, business_name=business_name, view=view)


def test_renders_tiles_strip_shapes_and_tokens():
    tiles = [
        ModuleTile("caja", "Resultado", "?tab=expenses", "USD 1.4k", "acumulado", "good", "ok", "Operación"),
        ModuleTile("stock", "Stock", "?tab=stock", "505 u", "1 bajo", "warn", "ok", "Operación"),
        ModuleTile("ventas", "Ventas semana", "?tab=sales", "USD 1.9k", "3 ventas", "good", "ok", "Operación"),
        ModuleTile("costos", "Margen", "?tab=x", "—", "no disponible", "warn", "degraded", "Operación"),
    ]
    att = [
        AttentionItem(Severity.HIGH, "Stock bajo: Pulsera quedan 5 u", "Reponer", "?tab=stock", "stock"),
        AttentionItem(Severity.MID, "Algo medio", "Ver", "?tab=sales", "ventas"),
        AttentionItem(Severity.LOW, "Nota menor", "Ver", "?tab=x", "x"),
    ]
    view = HomeView(tiles=tiles, attention=att, rail_groups=_rail_groups(tiles))
    html = _render(view)

    assert "#4F46E5" in html and "JetBrains+Mono" in html  # design tokens + money font
    assert "Atención · 3 cosas" in html
    # severity shapes, not colour alone
    assert '<span class="ic"><span class="tri"></span>' in html
    assert '<span class="ic"><span class="cir"></span>' in html
    assert '<span class="ic"><span class="ciro"></span>' in html
    # live tiles + honest degraded tile
    assert "505 u" in html and "USD 1.4k" in html
    assert "no disponible" in html and "degraded" in html
    # drill-down honours the module route
    assert "/tenants/+100?tab=stock" in html
    assert "Todavía no hay datos" not in html  # not empty
    # no fabricated direction arrow
    assert "▲" not in html and "&#9650;" not in html


def test_renders_empty_state_for_fresh_tenant():
    tiles = [ModuleTile("caja", "Resultado", "?tab=expenses", "USD 0", "sin movimientos", "flat", "empty", "Operación")]
    view = HomeView(tiles=tiles, attention=[], rail_groups=_rail_groups(tiles))
    html = _render(view)
    assert "Todavía no hay datos" in html


def test_all_degraded_renders_scorecard_not_welcome():
    tiles = [
        ModuleTile("caja", "Resultado", "?tab=expenses", "—", "no disponible", "warn", "degraded", "Operación"),
        ModuleTile("stock", "Stock", "?tab=stock", "—", "no disponible", "warn", "degraded", "Operación"),
    ]
    view = HomeView(tiles=tiles, attention=[], rail_groups=_rail_groups(tiles))
    html = _render(view)
    assert "Todavía no hay datos" not in html  # outage is visible, not a false welcome
    assert "no disponible" in html
