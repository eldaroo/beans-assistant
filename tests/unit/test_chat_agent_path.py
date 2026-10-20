"""Chat on the native tool-use agent (spec 007). Since M5 retired the LangGraph, the agent
path is the only path (no cutover flag). These pin the command-center side deterministically:
the persona/system prompt, and that _invoke_agent drives the gateway client with the built
context and returns its text.
"""
from backend.services.chat_service import ChatService


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
