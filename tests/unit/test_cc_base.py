"""cc_base.html tests (spec 004 S1-shell + T-002 shared components; spec 006 M1
three-tab reshape).

The single owner-facing base. These assert the shell it carries — the three-tab
rail from `tabs` (spec 006 AC1, which replaced the per-module left rail), the
topbar theme toggle, the modern tokens — the extends relationship, and the T-002
shared components (empty-state, skeleton, page-enter). The home's own
no-number-regressed self-regression is covered by
`test_shell_reshape_regression.py`.
"""
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.modules import nav

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"


def _env():
    return Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)


def test_base_file_exists_and_carries_the_shell():
    src = (_TEMPLATES / "cc_base.html").read_text(encoding="utf-8")
    # modern tokens (indigo light + dark), the money font, the shadow-strip token.
    assert "#4F46E5" in src and "#818CF8" in src
    assert "JetBrains+Mono" in src and "--shadow-strip" in src
    # three-tab rail (spec 006, replaced the per-module left rail), topbar theme
    # toggle, blocks a page fills.
    assert 'class="cc-tabs"' in src and 'role="tablist"' in src and 'id="themebtn"' in src
    assert "{% block content %}" in src and "{% block chat %}" in src and "{% block page_css %}" in src


def test_shared_components_present():
    """T-002: one empty-state, one skeleton loader, one page-enter, all in the base."""
    src = (_TEMPLATES / "cc_base.html").read_text(encoding="utf-8")
    assert ".cc-empty" in src and ".cc-skeleton" in src
    assert ".cc-main-enter" in src              # page-enter for non-home pages
    assert "@keyframes rise" in src and "@keyframes cc-shimmer" in src
    assert "prefers-reduced-motion:reduce" in src  # motion honoured


def test_home_extends_the_base():
    src = (_TEMPLATES / "control_center.html").read_text(encoding="utf-8")
    assert '{% extends "cc_base.html" %}' in src
    # the home no longer carries its own <head>/doctype; the base owns them.
    assert "<!doctype html>" not in src


def test_base_renders_three_tab_rail_from_tabs_with_active_selected():
    """A page extending the base renders the three tabs from `tabs`, with the
    active tab marked aria-selected and each tab linking to the home (#tabid).
    The active tab reflects the module's group (here a productos page -> Operación)."""
    tpl = _env().from_string(
        '{% extends "cc_base.html" %}{% block content %}<p id="x">hola</p>{% endblock %}'
    )
    html = tpl.render(
        business_name="Beans&Co", phone="+100",
        tabs=nav.owner_tabs(), active_tab="operacion", active_route="productos",
    )
    assert '<p id="x">hola</p>' in html
    assert 'role="tablist"' in html
    # the three owner tabs render
    assert 'data-cc-tab="hoy"' in html and 'data-cc-tab="operacion"' in html and 'data-cc-tab="costos"' in html
    assert "Operación" in html and "Costos y producción" in html
    # the active tab is selected, the others are not
    op = re.search(r'<a[^>]*data-cc-tab="operacion"[^>]*>', html)
    assert op and 'aria-selected="true"' in op.group(0)
    hoy = re.search(r'<a[^>]*data-cc-tab="hoy"[^>]*>', html)
    assert hoy and 'aria-selected="false"' in hoy.group(0)
    # tabs link to the home with the tab preselected via ?tab= (phone-less,
    # single business), so a tab is reachable and deep-linkable with JS off
    assert 'href="/home?tab=hoy"' in html


def test_base_renders_without_tabs():
    """A page that passes no tabs still renders the shell (an empty tab rail)."""
    html = _env().from_string(
        '{% extends "cc_base.html" %}{% block content %}<p>ok</p>{% endblock %}'
    ).render(business_name="Beans&Co", phone="+100")
    assert "<p>ok</p>" in html
    assert 'class="cc-tabs"' in html and 'id="themebtn"' in html
