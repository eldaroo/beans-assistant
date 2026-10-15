"""Timonel slot tests (spec 004, S7 + T-004).

The shared chat slot is mounted once in cc_base.html's chat block, so it appears
on the home and every owner page that extends the base. It reuses the existing
window.beansChat Alpine factory over the real tenant chat endpoint, in a plain
modern-token shell (no Tailwind, no legacy --color-* tokens). Cohort A ships the
slot present + openable + floating-by-default; the cross-document refresh
contract (AC8) is Cohort D.
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.modules.home_service import HomeView, _rail_groups
from backend.modules.protocol import ModuleTile

_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES = _ROOT / "backend" / "templates"


def _env():
    return Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)


def _home_html():
    tiles = [ModuleTile("caja", "Resultado", "?tab=expenses", "USD 1.4k", "acumulado", "good", "ok", "Operación")]
    view = HomeView(tiles=tiles, attention=[], rail_groups=_rail_groups(tiles))
    return _env().get_template("control_center.html").render(
        phone="+100", business_name="Beans&Co", view=view, nav=view.rail_groups, active_route="home"
    )


def test_base_includes_the_slot_partial():
    base = (_TEMPLATES / "cc_base.html").read_text(encoding="utf-8")
    assert '{% include "_timonel_slot.html" %}' in base
    # Alpine + the factory are loaded so the slot has something to bind to.
    assert "alpinejs@3.14.1" in base
    assert "/static/js/chat_widget.js" in base


def test_slot_appears_on_the_home_bound_to_the_factory():
    html = _home_html()
    # the factory is bound for this tenant, floating-by-default (calm home)
    assert 'beansChat({ phone: "+100"' in html and 'dock: "floating" })' in html
    # launcher + dialog affordances present
    assert 'class="tim-launch"' in html and "Timonel" in html
    assert 'x-ref="input"' in html and 'x-model="input"' in html
    assert '@submit.prevent="send(input)"' in html
    # Alpine + factory script on the page
    assert "alpinejs@3.14.1" in html and "/static/js/chat_widget.js" in html


def test_slot_is_plain_modern_css_not_tailwind_or_legacy_tokens():
    src = (_TEMPLATES / "_timonel_slot.html").read_text(encoding="utf-8")
    # no legacy --color-* token names (those belong to the coffee legacy base)
    assert "--color-brand" not in src and "--color-surface" not in src
    # uses the modern Control Center tokens instead
    assert "var(--accent)" in src and "var(--card)" in src
    # the bubble styling is local (we do not call bubbleClass, which returns Tailwind)
    assert ".tim-bubble" in src and 'bubbleClass' not in src
    # 44px touch targets + focus rings honoured (accessibility)
    assert "min-height:44px" in src and "focus-visible" in src


def test_factory_supports_floating_dock_override():
    """The slot asks for a floating default; the factory honours an initial-dock
    override while still preferring the user's persisted choice."""
    js = (_ROOT / "backend" / "static" / "js" / "chat_widget.js").read_text(encoding="utf-8")
    assert "arg.dock === 'pinned' || arg.dock === 'floating'" in js
    assert "_defaultDock: cfg.dock || DEFAULT_DOCK" in js
    assert "? saved : this._defaultDock" in js
