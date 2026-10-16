"""Read-only pages migrated onto cc_base (spec 004, S6 + T-003).

costos / produccion / logistica / proveedores each now extend cc_base.html, so
they wear the one owner brand with the held rail, the topbar theme toggle, and
Timonel — instead of a lone centered column with a back-link. Their content
(the data cards) is unchanged; the populated-data render is covered by the four
integration page tests. These assert the migration invariants: the extends
relationship, the shell on every page, the active rail item, and that each
page kept its own content styling.
"""
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
        nav=nav.owner_rail("+100"), active_route=active,
    )


@pytest.mark.parametrize("tpl", list(PAGES))
def test_page_extends_base_and_drops_its_own_doctype(tpl):
    src = (_TEMPLATES / tpl).read_text(encoding="utf-8")
    assert '{% extends "cc_base.html" %}' in src
    assert "<!doctype html>" not in src          # the base owns the document
    assert PAGES[tpl][1] in src                   # kept its own content CSS


@pytest.mark.parametrize("tpl", list(PAGES))
def test_page_renders_shell_rail_timonel_and_active_item(tpl):
    active, _ = PAGES[tpl]
    html = _render(tpl, active)
    # the held rail with every module, the topbar theme toggle, Timonel slot
    assert 'class="rail"' in html and 'id="themebtn"' in html
    assert 'beansChat({ phone: "+100"' in html and 'class="tim-launch"' in html
    assert ">Costos<" in html and ">Stock<" in html and ">Ventas semana<" in html
    # this page's own rail item is current, linking to its absolute route
    assert 'aria-current="true" href="/%s"' % active in html
    # back-link preserved (content-level self-regression) + Inicio in rail
    assert "Volver al inicio" in html and 'href="/home"' in html


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
