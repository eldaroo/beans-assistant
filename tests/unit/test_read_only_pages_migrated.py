"""Read-only pages migrated onto cc_base (spec 004, S6 + T-003).

costos / produccion / logistica / proveedores each now extend cc_base.html, so
they wear the one owner brand with the held rail, the topbar theme toggle, and
Timonel — instead of a lone centered column with a back-link. Their content
(the data cards) is unchanged; the populated-data render is covered by the four
integration page tests. These assert the migration invariants: the extends
relationship, the shell on every page, the active rail item, and that each
page kept its own content styling.
"""
import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from backend.modules import nav

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"

# page template -> (active module id, a content-CSS marker unique to that page)
PAGES = {
    "costos.html": ("costos", ".total{"),
    "produccion.html": ("produccion", ".units{"),
    "logistica.html": ("logistica", "ul.rows li{"),
    "proveedores.html": ("proveedores", ".rows .chip.ok{"),
}


def _render(tpl, active):
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)
    return env.get_template(tpl).render(
        phone="+100", view=None, business_name="Beans&Co",
        nav=nav.owner_rail("+100"),
        tabs=nav.owner_tabs(), active_tab=nav.tab_id_for_module(active),
        active_route=active,
    )


@pytest.mark.parametrize("tpl", list(PAGES))
def test_page_extends_base_and_drops_its_own_doctype(tpl):
    src = (_TEMPLATES / tpl).read_text(encoding="utf-8")
    assert '{% extends "cc_base.html" %}' in src
    assert "<!doctype html>" not in src          # the base owns the document
    assert PAGES[tpl][1] in src                   # kept its own content CSS


@pytest.mark.parametrize("tpl", list(PAGES))
def test_page_renders_shell_tabs_timonel_and_active_tab(tpl):
    """spec 006 T-005: each module page renders inside its tab context — the
    three-tab rail with the module's group tab selected (replacing the old held
    per-module rail), the topbar theme toggle, and the Timonel slot."""
    active, _ = PAGES[tpl]
    html = _render(tpl, active)
    # the three-tab rail, the topbar theme toggle, Timonel slot
    assert 'class="cc-tabs"' in html and 'role="tablist"' in html and 'id="themebtn"' in html
    assert 'beansChat({ phone: "+100"' in html and 'class="tim-launcher"' in html
    assert 'data-cc-tab="hoy"' in html and 'data-cc-tab="operacion"' in html and 'data-cc-tab="costos"' in html
    assert "Operación" in html and "Costos y producción" in html
    # this page sits under its group's tab, which is the selected tab
    want = nav.tab_id_for_module(active)
    m = re.search(r'<a[^>]*data-cc-tab="%s"[^>]*>' % want, html)
    assert m and 'aria-selected="true"' in m.group(0)
    # back-link preserved (content-level self-regression) + the Hoy tab links home
    assert "Volver al inicio" in html and 'href="/home?tab=hoy"' in html


def test_owner_rail_is_snapshot_free():
    """A module page's rail is built from descriptors, not the home's fan-out:
    it carries all seven modules in registry order with no DB read."""
    groups = nav.owner_rail("+100")
    labels = [it.label for g in groups for it in g.items]
    assert labels == ["Resultado", "Productos", "Stock", "Ventas semana", "Costos", "Producción", "Logística", "Proveedores"]
    # absolute routes stay absolute (page modules), legacy tabs stay tabs
    routes = {it.module_id: it.route for g in groups for it in g.items}
    # stock is repointed to its own page in Cohort B (T-007); no longer a legacy tab.
    assert routes["costos"] == "/costos/{phone}" and routes["stock"] == "/stock/{phone}"
