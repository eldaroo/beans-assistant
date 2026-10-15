"""cc_base.html tests (spec 004, S1-shell + T-002 shared components).

The single owner-facing base extracted from the shipped home. These assert the
shell it carries (held rail from `nav`, topbar theme toggle, modern tokens), the
extends relationship, and the T-002 shared components (empty-state, skeleton,
page-enter). The home's own byte-for-byte self-regression is covered by the
control-center template/route tests (the home keeps its tiles/strip markup; the
base only adds the shell), and was proven at build time by a DOM-identity diff of
the pre-rebase home against the re-based home.
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"


def _env():
    return Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)


def _nav():
    # One rail group with two module items, same shape home_service._rail_groups emits.
    class _Tile:
        def __init__(self, mid, label, route):
            self.module_id, self.label, self.route = mid, label, route

    class _Group:
        def __init__(self, label, items):
            self.label, self.items = label, items

    return [_Group("Operación", [_Tile("stock", "Stock", "?tab=stock"), _Tile("ventas", "Ventas", "/ventas/{phone}")])]


def test_base_file_exists_and_carries_the_shell():
    src = (_TEMPLATES / "cc_base.html").read_text(encoding="utf-8")
    # modern tokens (indigo light + dark), the money font, the shadow-strip token.
    assert "#4F46E5" in src and "#818CF8" in src
    assert "JetBrains+Mono" in src and "--shadow-strip" in src
    # held rail, topbar theme toggle, blocks a page fills.
    assert 'class="rail"' in src and 'id="themebtn"' in src
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


def test_base_renders_held_rail_from_nav_with_active_current():
    """A minimal page extending the base renders the rail items from `nav`, with
    the Inicio link marked current on the home and a module link resolving through
    href_for (an absolute route is tenant-filled; a legacy tab falls through)."""
    env = _env()
    env.loader.mapping = {}  # not used; FileSystemLoader resolves cc_base from disk
    tpl = env.from_string(
        '{% extends "cc_base.html" %}{% block content %}<p id="x">hola</p>{% endblock %}'
    )
    html = tpl.render(business_name="Beans&Co", phone="+100", nav=_nav(), active_route="home")
    assert '<p id="x">hola</p>' in html
    assert 'href="/home/+100"' in html and 'aria-current="true"' in html  # Inicio current
    assert ">Stock<" in html and ">Ventas<" in html                       # rail items
    assert "/tenants/+100?tab=stock" in html                              # legacy tab still falls through
    assert "/ventas/+100" in html                                         # absolute route tenant-filled
    assert 'railsep">Operación' in html


def test_base_renders_without_nav():
    """A page that passes no nav still renders the shell (rail shows only Inicio)."""
    html = _env().from_string(
        '{% extends "cc_base.html" %}{% block content %}<p>ok</p>{% endblock %}'
    ).render(business_name="Beans&Co", phone="+100")
    assert "<p>ok</p>" in html and 'href="/home/+100"' in html
