"""Owner surface demote-legacy crawl (spec 004, S8-demote-legacy / T-012 / AC9).

AC9: a crawl of the owner-facing routes (/home and every tile route) finds no
link, redirect, or href_for fallthrough that resolves to /tenants/{phone}; the
empty-state card no longer links to the legacy base; /tenants/{phone} still
exists as the Admin-only fallback.

Three deterministic layers, no live Postgres:

1. href_for never falls through to /tenants/ for any REGISTERED module route
   (the rail + tiles + attention are all registry-route-driven). The macro only
   falls through for a legacy '?tab=' route, and cohorts B/C repointed every
   module route to an absolute '/...'; this asserts the registry stayed clean.
2. A source crawl of every OWNER template finds no owner-facing anchor/redirect
   to /tenants/ (the /api/tenants/ write endpoints are allowed — they are the
   CRUD path, not a page link).
3. The home renders in BOTH states (populated + the empty-state card) with no
   /tenants/ owner link, and the empty-state CTA now points at /productos.
   The legacy /tenants/{phone} route is still registered on the app.
"""
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.modules import nav, registry

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"

# The owner-facing surface. Everything the home and the tile routes render,
# plus the shared base/slot/macros they all pull in. The legacy base.html,
# tenant_detail.html, and tenants.html are the Admin-only fallback and are
# deliberately NOT crawled (they stay live, unchanged — Out of scope).
# NOTE: _cc_macros.html is deliberately NOT in this raw-source list. It is the
# DEFINITION of href_for, whose non-'/' fallthrough branch literally contains
# "/tenants/{{ phone }}" as the guarded legacy escape hatch. That branch is
# exercised only by a '?tab=' route (none remain in the registry) and is covered
# directly by test_href_for_never_falls_through_for_registered_routes and
# test_href_for_still_falls_through_for_a_legacy_tab — it is not a rendered
# owner-facing link, so scanning the macro body for the literal would be a false
# positive on the very mechanism that proves the surface is clean.
_OWNER_TEMPLATES = [
    "cc_base.html",
    "_timonel_slot.html",
    "control_center.html",
    "productos.html",
    "stock.html",
    "ventas.html",
    "resultado.html",
    "costos.html",
    "produccion.html",
    "logistica.html",
    "proveedores.html",
]

# An owner-facing link into legacy: /tenants/{...} NOT preceded by /api (the
# /api/tenants/ REST endpoints are the reused write path, not a page link).
_LEGACY_LINK = re.compile(r"(?<!/api)/tenants/")

# Jinja comments {# ... #} / {#- ... -#} are documentation, not rendered output;
# a template docstring that explains "repointed off the legacy ?tab=expenses
# bounce" is prose, not a live link. Strip comments before a source scan so the
# scan reads only what actually renders.
_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)


def _rendered_source(name: str) -> str:
    return _JINJA_COMMENT.sub("", (_TEMPLATES / name).read_text(encoding="utf-8"))


def _env():
    return Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)


def _render_href_for(route: str, phone: str) -> str:
    tmpl = _env().from_string(
        "{% from '_cc_macros.html' import href_for %}{{ href_for(route, phone) }}"
    )
    return tmpl.render(route=route, phone=phone)


def test_href_for_never_falls_through_for_registered_routes():
    """Every registered module route is absolute, so href_for substitutes
    {phone} and never emits the /tenants/ legacy fallback (AC9)."""
    phone = "+5491100000001"
    for m in registry.all_modules():
        resolved = _render_href_for(m.route, phone)
        assert not _LEGACY_LINK.search(resolved), (
            f"module {m.id!r} route {m.route!r} resolved to a legacy link: {resolved!r}"
        )
        assert resolved.startswith("/"), resolved
        assert "/tenants/" not in resolved


def test_href_for_still_falls_through_for_a_legacy_tab():
    """Guard the macro's contract itself: a '?tab=' route (none remain in the
    registry) still falls through, so the test above is meaningful, not vacuous."""
    assert _render_href_for("?tab=stock", "+100") == "/tenants/+100?tab=stock"


def test_no_owner_template_links_into_legacy():
    """Source crawl: no owner template carries an owner-facing /tenants/ link.
    The /api/tenants/ CRUD endpoints are allowed (the reused write path)."""
    offenders = {}
    for name in _OWNER_TEMPLATES:
        src = _rendered_source(name)
        hits = _LEGACY_LINK.findall(src)
        if hits:
            offenders[name] = len(hits)
    assert not offenders, f"owner templates still link into legacy: {offenders}"


def test_no_owner_template_uses_a_legacy_tab_bounce():
    """Closes the latent path a raw /tenants/ scan misses (council Edut, Winston):
    an owner template could carry a legacy `?tab=` route literal (directly or via
    href_for('?tab=...')), which href_for renders to /tenants/{phone} at request
    time even though the SOURCE has no /tenants/ literal. Every tile/attention
    route moved to an absolute '/...' in cohorts B/C, so no owner template should
    reference `?tab=` at all."""
    offenders = {}
    for name in _OWNER_TEMPLATES:
        src = _rendered_source(name)
        if "?tab=" in src:
            offenders[name] = src.count("?tab=")
    assert not offenders, f"owner templates still reference a legacy ?tab= bounce: {offenders}"


def test_home_populated_has_no_legacy_link():
    view = {
        "is_empty": False,
        "attention": [],
        "tiles": [
            {"module_id": "stock", "label": "Stock", "route": "/stock/{phone}",
             "value": "505 u", "status": "ok", "trend": "", "trend_tone": "flat"},
        ],
    }
    html = _env().get_template("control_center.html").render(
        phone="+100", view=view, business_name="Beans&Co",
        nav=nav.owner_rail("+100"), active_route="home",
    )
    assert not _LEGACY_LINK.search(html), "populated home links into legacy"
    assert 'href="/stock"' in html and "/stock/+100" not in html  # tile route phone-less


def test_home_empty_state_cta_points_at_productos_not_legacy():
    view = {"is_empty": True, "attention": [], "tiles": []}
    html = _env().get_template("control_center.html").render(
        phone="+100", view=view, business_name="Beans&Co",
        nav=nav.owner_rail("+100"), active_route="home",
    )
    # The empty-state card renders (the only place the legacy CTA used to live).
    assert "Empezar por inventario" in html
    # It no longer links to the legacy base, it opens the native Productos page
    # (phone-less: the single-business surface resolves the tenant from the session).
    assert not _LEGACY_LINK.search(html), "empty-state home links into legacy"
    assert 'href="/productos"' in html and "/productos/+100" not in html


def test_legacy_route_still_registered_as_fallback():
    """AC9: /tenants/{phone} is not deleted — it stays reachable as the fallback.
    (It is gated by require_tenant_match, i.e. owner-or-admin for the tenant's own
    phone, not an admin-only surface; AC9 closes only the owner->legacy LINK
    boundary, not the auth boundary — council Tamir.)"""
    from backend.app import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/tenants/{phone}" in paths
