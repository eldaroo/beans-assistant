"""Chat cutover to the native tool-use agent (spec 007 M1).

The full loop (gateway -> claude child -> beans MCP -> internal API) is proven live; these pin the
command-center side deterministically: the cutover flag, the persona/system prompt, and that
_invoke_agent drives the gateway client with the built context and returns its text.
"""
import backend.services.chat_service as chat_mod
from backend.services.chat_service import ChatService


def test_use_agent_flag(monkeypatch):
    monkeypatch.delenv("BEANS_CHAT_AGENT", raising=False)
    assert ChatService._use_agent() is False
    monkeypatch.setenv("BEANS_CHAT_AGENT", "1")
    assert ChatService._use_agent() is True
    monkeypatch.setenv("BEANS_CHAT_AGENT", "0")
    assert ChatService._use_agent() is False


def test_agent_system_prompt_is_timonel_and_honest():
    p = ChatService._agent_system_prompt("Dario")
    assert "Timonel" in p
    assert "Beans" in p
    assert "Dario" in p
    # Honesty rails: never invent numbers, say so when a tool is missing.
    assert "nunca inventes" in p.lower()
    assert "honestidad" in p.lower()


def test_invoke_agent_drives_the_gateway_with_context_and_returns_text(monkeypatch):
    seen = {}

    def fake_call_agent(system, prompt, **kwargs):
        seen["system"] = system
        seen["prompt"] = prompt
        return "Te quedan 48 unidades de la Pulsera Cafe Clasica."

    import llm_gateway
    monkeypatch.setattr(llm_gateway, "call_agent", fake_call_agent)

    out = ChatService._invoke_agent("+5491100000001", "cuanto stock de la clasica", owner_name="Dario")
    assert out.startswith("Te quedan 48")
    assert "Timonel" in seen["system"]
    # The current message reaches the gateway (empty history -> message passes through).
    assert "cuanto stock de la clasica" in seen["prompt"]
