"""Timonel voice-first shell + persistence + nav-router (spec 006 M2).

Structural verification of the M2 cohort that has no Python surface of its own:
the voice-first launcher and drawer/sheet (T-007), the chat persistence +
rehydration wiring (T-008/T-009), the shell beans:navigate {tab, module} router
and its module map (T-011), and the audio/STT control (T-012). The live
behaviour (sessionStorage survives a tab switch; the mic transcribes) is a
browser walk; these tests prove the container, the CSS and the client code that
carry that behaviour are present and the module map is valid JSON.
"""
import json
import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from backend.modules import nav

_TEMPLATES = Path(__file__).resolve().parents[2] / "backend" / "templates"
_STATIC = Path(__file__).resolve().parents[2] / "backend" / "static"


def _render_base():
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)
    tpl = env.from_string(
        '{% extends "cc_base.html" %}{% block content %}<p id="x">hola</p>{% endblock %}'
    )
    return tpl.render(
        business_name="Beans&Co", phone="+100",
        tabs=nav.owner_tabs(), active_tab="hoy", active_route="home",
    )


@pytest.mark.unit
def test_launcher_opens_drawer_and_never_hot_mics():
    """T-007 (revised): a launcher, collapsed by default, that ONLY opens the
    drawer. Regression guard: tapping the launcher must never auto-start the
    mic (the old voice-first "open + record in one tap" hot-mic'd the owner;
    Dario flagged it in prod). Voice stays an explicit composer action — see
    test_mic_control_and_recording_bar_present."""
    html = _render_base()
    assert 'class="tim-launcher"' in html
    # the launcher opens the drawer and does NOT engage the microphone.
    launcher = html.split('class="tim-launcher"', 1)[1].split("</button>", 1)[0]
    assert "@click=\"open()\"" in launcher
    assert "startRecording()" not in launcher, "launcher must not hot-mic"
    # it is collapsed by default (shown only when not open).
    assert 'x-show="!isOpen"' in html
    # drawer on desktop, bottom sheet on mobile.
    assert "tim-drawer" in html
    assert "translateX(103%)" in html          # drawer offscreen by default
    assert "translateY(103%)" in html          # bottom sheet on mobile
    assert "max-width:900px" in html           # the sheet breakpoint
    # single mount of the factory (D-030).
    assert html.count("x-data='beansChat(") == 1


@pytest.mark.unit
def test_mic_control_and_recording_bar_present():
    """T-012: a mic toggle in the composer and a visible recording bar.

    Regression guard (2026-10-21, wal-ledger parity): the mic must NEVER be a
    dead/disabled button. The old `:disabled="!micSupported"` greyed it out when
    the load-time feature check read false, which is the prod "botón del
    micrófono gris, no se puede tocar" report. The mic is now always tappable —
    toggleRecording() re-checks support at click time and degrades to typing when
    speech recognition is genuinely absent — so the composer's ONLY disabled
    control is the send button, never the mic."""
    html = _render_base()
    assert 'class="tim-mic"' in html
    assert "toggleRecording()" in html
    # the mic button carries no :disabled binding (scope the check to the button).
    mic_btn = html.split('class="tim-mic"', 1)[1].split("</button>", 1)[0]
    assert ":disabled" not in mic_btn, "mic must never be a dead/disabled button"
    assert 'class="rec-bar"' in html
    assert "recTimeLabel()" in html
    assert "Grabando audio" in html


@pytest.mark.unit
def test_shell_router_and_module_map_present_and_valid():
    """T-011: the {tab, module} router listener and a valid module map."""
    html = _render_base()
    assert 'id="cc-modules"' in html
    assert 'addEventListener("beans:navigate"' in html
    # the module map is valid JSON and covers the registered modules.
    m = re.search(r'<script id="cc-modules"[^>]*>(.*?)</script>', html, re.S)
    assert m, "cc-modules script not rendered"
    triples = json.loads(m.group(1))
    ids = {t[0] for t in triples}
    assert {"caja", "productos", "stock", "ventas", "costos"}.issubset(ids)
    # each triple is [module_id, route, tab_id]; routes carry the {phone} token
    by_id = {t[0]: t for t in triples}
    assert by_id["stock"][1] == "/stock/{phone}"
    assert by_id["stock"][2] == "operacion"
    assert by_id["costos"][2] == "costos"


@pytest.mark.unit
def test_chat_widget_js_carries_persistence_rehydration_and_voice():
    """T-008/T-009/T-012: the factory methods the shell binds to exist."""
    src = (_STATIC / "js" / "chat_widget.js").read_text(encoding="utf-8")
    # persistence (T-008)
    assert "_saveThread" in src and "_rehydrateFromSession" in src
    assert "beans:thread:" in src and "sessionStorage" in src
    # server rehydration (T-009)
    assert "_rehydrateFromServer" in src and "/chat/thread" in src
    # voice input (T-012): real STT path. The transcription is placed in the
    # composer for the owner to review and send (never auto-sent), so she always
    # sees what Timonel heard before it acts (Edut) — M2 has no confirm floor yet.
    assert "startRecording" in src and "SpeechRecognition" in src
    assert "self.input = said" in src          # transcription -> composer for review
    assert "self.send(said)" not in src        # never auto-send a spoken turn in M2


@pytest.mark.unit
def test_bridge_defers_owner_form_to_shell_router():
    """T-011/D-031: the legacy bridge skips the {tab, module} owner form."""
    src = (_STATIC / "js" / "cc_chat_bridge.js").read_text(encoding="utf-8")
    assert "if (detail.module) return;" in src
