"""Shell-reshape self-regression (spec 006 M1, AC12 / T-006): no number regressed.

The three-tab reshape changes the shell CHROME (the left rail became a top
three-tab bar) but must not drop or alter a single number the home renders. The
influex-scoped ``bin/qie pixel`` fidelity gate is the wrong instrument for a
deliberate chrome reshape (a full-image diff would flag the intended rail->tabs
change as a failure); the exact "no number regressed" proof is a content
contract on the painted numbers, matching the DOM/content-identity pattern this
repo's prior cohorts used.

DURABILITY NOTE: a one-shot render diff of the home at git HEAD versus the
working tree (same viewmodel) was run GREEN at build time to confirm the
reshaped Hoy content is byte-equal to the pre-reshape home. That comparison can
only run while the reshape is uncommitted (once committed, ``HEAD`` IS the
reshaped template and the diff is self-vs-self), so it is NOT the durable guard.
The durable CI guard below is a self-contained content contract: render the
reshaped home with a KNOWN viewmodel and assert the Hoy panel paints every tile
value/label/trend and every attention line that viewmodel carries, in order, and
that Hoy's number set equals all tiles. It protects every future change too, and
never self-destructs on the commit that lands it.
"""
from __future__ import annotations

import re
from pathlib import Path

import jinja2
import pytest

from backend.modules import home_service, nav
from backend.modules.protocol import AttentionItem, ModuleTile, Severity

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"


@pytest.fixture
def working_env():
    return jinja2.Environment(loader=jinja2.FileSystemLoader(str(_TEMPLATES)), autoescape=True)


def _tile(mid, value, trend=None, tone="flat"):
    return ModuleTile(
        module_id=mid, label=mid.title(), route=f"/{mid}/{{phone}}",
        value=value, trend=trend, trend_tone=tone, status="ok",
    )


def _fixture_view():
    # Distinct values so a misrouted or dropped tile shows up as a wrong/missing
    # number. The registry order is caja, productos, stock, ventas (Operación),
    # then costos, produccion, logistica, proveedores (Costos y producción).
    tiles = [
        _tile("caja", "USD 3.7k", "ganancia del mes", "good"),
        _tile("productos", "12"),
        _tile("stock", "540 u"),
        _tile("ventas", "USD 1.9k"),
        _tile("costos", "USD 2.10"),
        _tile("produccion", "320 u"),
        _tile("logistica", "2 rutas"),
        _tile("proveedores", "3", "1 vencido", "warn"),
    ]
    attention = [
        AttentionItem(severity=Severity.HIGH, text="Termos Alumbrar sin stock", action_label="Reponer", route="/stock/{phone}", module_id="stock"),
        AttentionItem(severity=Severity.MID, text="Check-in de Maderas del Sur vencido", action_label="Ver", route="/proveedores/{phone}", module_id="proveedores"),
    ]
    return home_service.HomeView(tiles=tiles, attention=attention, rail_groups=[])


def _render(working_env, view, active_tab="hoy"):
    tabs = nav.owner_tabs()
    return working_env.get_template("control_center.html").render(
        phone="549", business_name="Beans&Co", view=view,
        tabs=tabs, tab_tiles=home_service.tiles_by_tab(view, tabs),
        active_tab=active_tab, active_route="home",
    )


def _panel(html, pid):
    m = re.search(rf'<section[^>]*data-cc-panel="{pid}".*?</section>', html, re.S)
    assert m, f"home must carry the {pid} tab panel"
    return m.group(0)


def _labels(html):
    return [m.strip() for m in re.findall(r'<span class="lbl">(.*?)</span>', html, re.S)]


def _nums(html):
    return [m.strip() for m in re.findall(r'<span class="num">(.*?)</span>', html, re.S)]


def _trends(html):
    # strip the inner warn dot span first so the trend regex captures just the text
    cleaned = re.sub(r'<span class="dot"></span>', "", html)
    return [m.strip() for m in re.findall(r'<span class="trend [^"]*">(.*?)</span>', cleaned, re.S)]


def _attention_texts(html):
    return [m.strip() for m in re.findall(r'<span class="txt">(.*?)</span>', html, re.S)]


def test_hoy_panel_paints_every_viewmodel_number_in_order(working_env):
    view = _fixture_view()
    hoy = _panel(_render(working_env, view), "hoy")
    # Every tile value and label the viewmodel carries is painted, in registry
    # order, by the Hoy panel — nothing dropped, nothing reordered, nothing altered.
    assert _nums(hoy) == [t.value for t in view.tiles]
    assert _labels(hoy) == [t.label for t in view.tiles]
    assert len(_nums(hoy)) == 8
    # trend captions are preserved for the tiles that carry one (caja, proveedores)
    assert _trends(hoy) == ["ganancia del mes", "1 vencido"]
    # the attention strip lines are preserved, in order
    assert _attention_texts(hoy) == [a.text for a in view.attention]


def test_job_tabs_show_only_their_group_numbers(working_env):
    view = _fixture_view()
    html = _render(working_env, view)
    op = _panel(html, "operacion")
    co = _panel(html, "costos")
    assert _nums(op) == ["USD 3.7k", "12", "540 u", "USD 1.9k"]  # Operación's 4
    assert _nums(co) == ["USD 2.10", "320 u", "2 rutas", "3"]    # Costos' 4
    # the two job tabs partition the eight, Hoy shows the union
    assert len(_nums(op)) == 4 and len(_nums(co)) == 4


def test_server_selected_active_tab_unhides_that_panel(working_env):
    # A ?tab=operacion deep-link sets active_tab server-side; the Operación panel
    # is rendered visible and Hoy hidden, so the tab is reachable with JS off.
    view = _fixture_view()
    html = _render(working_env, view, active_tab="operacion")
    op_tag = re.search(r'<section[^>]*data-cc-panel="operacion"[^>]*>', html).group(0)
    hoy_tag = re.search(r'<section[^>]*data-cc-panel="hoy"[^>]*>', html).group(0)
    assert "hidden" not in op_tag, "server-selected tab panel must be visible without JS"
    assert "hidden" in hoy_tag, "non-active panels are hidden server-side"


def test_fresh_tenant_job_tabs_guide_instead_of_painting_empty_tiles(working_env):
    # A fresh tenant (every tile EMPTY) must not show a grid of "—" tiles under
    # Operación/Costos with no cue; it shows the honest "arma sola" guidance.
    tiles = [ModuleTile(module_id="caja", label="Resultado", route="/resultado/{phone}",
                        value="USD 0", trend="sin movimientos", trend_tone="flat", status="empty")]
    view = home_service.HomeView(tiles=tiles, attention=[], rail_groups=[])
    html = _render(working_env, view)
    op = _panel(html, "operacion")
    assert "cc-empty" in op and "se arma sola" in op
    assert _nums(op) == []  # no empty tiles painted under the job tab
