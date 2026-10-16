"""Chat-to-screen refresh contract (spec 004, S7 / T-011 / AC8).

Timonel is mounted once in cc_base and emits beans:refresh (every clean turn)
and beans:navigate (only when a tool executed). Split across separate documents,
the contract is re-established by cc_chat_bridge.js plus a per-page ccRefetch
hook. These assert the shipped wiring (the JS behaviour itself is proven by the
served-render fetch-stub walk in the run demonstration):

- cc_base mounts Timonel once, exposes data-cc-phone, and loads the bridge.
- the bridge maps the four navigable domains to their four owner pages and
  listens for both events (so it never claims a screen it cannot reach).
- each CRUD page registers window.ccRefetch in its Alpine init, so beans:refresh
  refetches the page the owner is on.
"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / "backend"
_TEMPLATES = _ROOT / "templates"
_STATIC = _ROOT / "static" / "js"


def _tmpl(name: str) -> str:
    return (_TEMPLATES / name).read_text(encoding="utf-8")


def test_cc_base_mounts_timonel_once_and_loads_the_bridge():
    src = _tmpl("cc_base.html")
    # Timonel slot included exactly once from the base's chat block.
    assert src.count('include "_timonel_slot.html"') == 1
    # The bridge needs the tenant phone to build cross-document routes.
    assert 'data-cc-phone="{{ phone }}"' in src
    # The bridge ships after the widget (it consumes the widget's events).
    assert "cc_chat_bridge.js" in src
    assert src.index("chat_widget.js") < src.index("cc_chat_bridge.js")


def test_bridge_listens_for_both_events():
    src = (_STATIC / "cc_chat_bridge.js").read_text(encoding="utf-8")
    assert "addEventListener('beans:refresh'" in src
    assert "addEventListener('beans:navigate'" in src
    # beans:refresh drives the page's own refetch hook.
    assert "window.ccRefetch" in src


def test_bridge_maps_every_navigable_domain_to_an_owner_page():
    """Honesty clause: all four domains resolve to a real page, so navigate
    never leaves a false 'X abierto' claim against an unreachable screen."""
    src = (_STATIC / "cc_chat_bridge.js").read_text(encoding="utf-8")
    assert "'/productos/'" in src   # products
    assert "'/stock/'" in src       # stock
    assert "'/ventas/'" in src      # sales
    assert "'/resultado/'" in src   # expenses live on Resultado (AC6)
    # Unknown domain returns null -> the bridge does not navigate to a dead screen.
    assert "default:" in src and "return null" in src


def test_every_crud_page_registers_ccrefetch_in_init():
    for name in ("productos.html", "stock.html", "ventas.html", "resultado.html"):
        src = _tmpl(name)
        assert "init:" in src, f"{name} has no Alpine init()"
        assert "window.ccRefetch" in src, f"{name} does not register the refetch hook"
        assert "self.refetch()" in src, f"{name} ccRefetch does not call its own refetch"


def test_home_has_no_refetch_hook_it_cannot_honour():
    """The server-rendered home has no in-place refetch, so it must NOT register
    ccRefetch (that would claim a refresh it cannot perform). A write turn
    navigates to the domain page instead; a read turn changes nothing."""
    assert "window.ccRefetch" not in _tmpl("control_center.html")
