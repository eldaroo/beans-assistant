"""Unit tests for the Hoy daily-truth headline (spec 006 T-010 / AC3).

The headline is a pure function over three plain inputs, so it is tested in
isolation from the home route that gathers those inputs. AC3's named case —
"two paid sales and one low-stock item" — is the first assertion.
"""
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from backend.modules import home_service, nav
from backend.modules.daily_truth import EMPTY_DAY, daily_truth_headline
from backend.modules.home_service import HomeView, _rail_groups
from backend.modules.protocol import ModuleTile

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"


def _render_hoy(daily_truth_line):
    tiles = [ModuleTile("ventas", "Ventas semana", "/ventas/{phone}", "USD 1.9k", "3 ventas", "good", "ok", "Operación")]
    view = HomeView(tiles=tiles, attention=[], rail_groups=_rail_groups(tiles))
    tabs = nav.owner_tabs()
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)
    return env.get_template("control_center.html").render(
        phone="+100", business_name="Beans&Co", view=view,
        tabs=tabs, tab_tiles=home_service.tiles_by_tab(view, tabs), active_tab=nav.HOY_ID,
        daily_truth=daily_truth_line,
    )


@pytest.mark.unit
def test_two_paid_sales_and_one_low_stock_item():
    """AC3 fixture: two paid sales today plus one low-stock attention item."""
    sentence = daily_truth_headline(
        paid_today=2,
        unpaid_today=0,
        top_attention="Stock bajo en Pulsera Azul (3 unidades)",
    )
    assert sentence == (
        "Hoy llevás 2 ventas cobradas. "
        "Lo más urgente: Stock bajo en Pulsera Azul (3 unidades)."
    )


@pytest.mark.unit
def test_empty_day_is_never_blank():
    """No sales, nothing to attend to -> the exact empty-day sentence (AC3)."""
    assert daily_truth_headline(0, 0, None) == EMPTY_DAY
    assert daily_truth_headline(0, 0, "   ") == EMPTY_DAY  # whitespace-only is empty


@pytest.mark.unit
def test_singular_pluralization():
    """One paid sale uses the singular noun; two use the plural."""
    assert daily_truth_headline(1, 0, None) == "Hoy llevás 1 venta cobrada."
    assert daily_truth_headline(3, 0, None) == "Hoy llevás 3 ventas cobradas."


@pytest.mark.unit
def test_paid_and_unpaid_compose_with_y():
    """Paid and unpaid clauses join with 'y' and pluralize independently."""
    assert daily_truth_headline(2, 1, None) == (
        "Hoy llevás 2 ventas cobradas y 1 pendiente de cobro."
    )
    assert daily_truth_headline(1, 2, None) == (
        "Hoy llevás 1 venta cobrada y 2 pendientes de cobro."
    )


@pytest.mark.unit
def test_only_unpaid_today():
    """A day with only pending sales still states them."""
    assert daily_truth_headline(0, 1, None) == "Hoy llevás 1 pendiente de cobro."


@pytest.mark.unit
def test_no_sales_but_attention_leads_with_the_urgent_item():
    """Quiet sales day but something needs attention -> lead with it."""
    assert daily_truth_headline(0, 0, "Cliente esperando respuesta") == (
        "Lo más urgente hoy: Cliente esperando respuesta."
    )


@pytest.mark.unit
def test_negative_or_none_counts_are_floored_to_zero():
    """Defensive: a None or negative count never crashes and reads as zero."""
    assert daily_truth_headline(None, None, None) == EMPTY_DAY  # type: ignore[arg-type]
    assert daily_truth_headline(-5, 0, None) == EMPTY_DAY


@pytest.mark.unit
def test_headline_renders_at_top_of_hoy_panel():
    """Wiring: the headline string renders in the Hoy panel (spec 006 T-010)."""
    line = daily_truth_headline(2, 0, "Stock bajo en Pulsera Azul (3 unidades)")
    html = _render_hoy(line)
    assert 'class="daily-truth"' in html
    assert "2 ventas cobradas" in html
    assert "Stock bajo en Pulsera Azul (3 unidades)" in html


@pytest.mark.unit
def test_hoy_omits_headline_element_when_blank():
    """A falsy headline leaves no empty element behind (belt for a None blip)."""
    html = _render_hoy("")
    assert 'class="daily-truth"' not in html
