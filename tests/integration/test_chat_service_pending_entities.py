"""Integration test for PR-A fix #3: pending_entities cross-turn flow.

Multi-turn flow exercised end-to-end through ChatService.chat_with_tenant
with the LangGraph mocked. Verifies turn 1 with missing_fields persists
pending_entities, and turn 2's router input gets the [Contexto:...]
marker built from that metadata.

Reproduces the captura at cp:20260508T052425Z:
- turn 1 user: "vendo medias, pantaletas y soquetes" -> bot asks for prices
- turn 2 user: "las medias 15, las pantaletas 20 y los soquetes todavia no lo se"
- expectation: turn 2 router sees the product names from turn 1.
"""
from unittest.mock import patch, MagicMock

import pytest

from backend.services.chat_service import ChatService


@pytest.fixture(autouse=True)
def _reset_history():
    ChatService._history_by_key.clear()
    ChatService._last_seen_by_key.clear()
    yield
    ChatService._history_by_key.clear()
    ChatService._last_seen_by_key.clear()


def _mock_tenant_manager(monkeypatch, phone: str):
    """Stub TenantManager so chat_with_tenant resolves to a real phone
    without hitting any actual tenant table."""
    from backend.services import chat_service as cs

    fake_manager = MagicMock()
    fake_manager.normalize_phone_number.return_value = phone
    fake_manager.resolve_tenant_phone.return_value = phone
    fake_manager.sanitize_owner_name.return_value = "Dario"
    fake_manager.set_tenant_owner_name.return_value = None
    fake_manager.get_tenant_config.return_value = {"owner_name": "Dario"}

    monkeypatch.setattr(cs, "TenantManager", lambda: fake_manager)

    # Bypass tenant_context (needs a tenant DB).
    from contextlib import contextmanager

    @contextmanager
    def fake_tenant_context(_phone):
        yield

    monkeypatch.setattr(cs, "tenant_context", fake_tenant_context)


@pytest.mark.integration
def test_turn1_missing_price_turn2_router_sees_pending_marker(monkeypatch):
    """Turn 1 leaves missing_fields=["unit_price_cents"] for product
    "medias"; turn 2 router input must contain the [Contexto:...] marker
    naming "medias"."""
    phone = "+5491153695627"
    _mock_tenant_manager(monkeypatch, phone)

    captured_inputs: list[str] = []

    def fake_invoke_turn1(state):
        captured_inputs.append(state["user_input"])
        return {
            "messages": [],
            "final_answer": "Me falta un dato: el precio de venta. Me lo podes decir?",
            "intent": "WRITE_OPERATION",
            "operation_type": "REGISTER_PRODUCT",
            "missing_fields": ["unit_price_cents"],
            "normalized_entities": {"name": "medias"},
        }

    def fake_invoke_turn2(state):
        captured_inputs.append(state["user_input"])
        return {
            "messages": [],
            "final_answer": "Listo, cargue medias a $15.",
            "intent": "WRITE_OPERATION",
            "operation_type": "REGISTER_PRODUCT",
            "missing_fields": [],
            "normalized_entities": {"name": "medias", "unit_price_cents": 1500},
        }

    fake_graph = MagicMock()

    # Turn 1.
    fake_graph.invoke.side_effect = fake_invoke_turn1
    with patch.object(ChatService, "_get_graph", return_value=fake_graph):
        ChatService.chat_with_tenant(phone, "vendo medias")

    assert len(captured_inputs) == 1
    assert "[Contexto:" not in captured_inputs[0]

    history_key = ChatService._history_key(phone)
    assistant_entry = next(
        e for e in ChatService._history_by_key[history_key]
        if e.get("role") == "assistant"
    )
    pending = (assistant_entry.get("metadata") or {}).get("pending_entities")
    assert pending is not None, "pending_entities must be persisted on turn 1"
    assert pending["operation_type"] == "REGISTER_PRODUCT"
    assert pending["items"][0]["name"] == "medias"
    assert pending["items"][0]["missing_fields"] == ["unit_price_cents"]

    # Turn 2.
    fake_graph.invoke.side_effect = fake_invoke_turn2
    with patch.object(ChatService, "_get_graph", return_value=fake_graph):
        ChatService.chat_with_tenant(phone, "las medias 15")

    assert len(captured_inputs) == 2
    turn2_input = captured_inputs[1]
    assert "[Contexto: turno anterior pidio el precio" in turn2_input
    assert "medias" in turn2_input
    assert "Mensaje actual: las medias 15" in turn2_input

    # And after the resolution, pending_entities is cleared on the latest
    # assistant entry (no missing_fields means nothing to chase forward).
    latest_assistant = [
        e for e in ChatService._history_by_key[history_key]
        if e.get("role") == "assistant"
    ][-1]
    assert "pending_entities" not in (latest_assistant.get("metadata") or {})


@pytest.mark.integration
def test_turn1_resolves_clean_no_pending_marker(monkeypatch):
    """Turn 1 with no missing_fields (clean WRITE_OPERATION) leaves no
    pending_entities. Turn 2 router input must not carry the marker."""
    phone = "+5491153695999"
    _mock_tenant_manager(monkeypatch, phone)

    captured_inputs: list[str] = []

    def fake_invoke(state):
        captured_inputs.append(state["user_input"])
        return {
            "messages": [],
            "final_answer": "Venta registrada.",
            "intent": "WRITE_OPERATION",
            "operation_type": "REGISTER_SALE",
            "missing_fields": [],
            "normalized_entities": {},
        }

    fake_graph = MagicMock()
    fake_graph.invoke.side_effect = fake_invoke

    with patch.object(ChatService, "_get_graph", return_value=fake_graph):
        ChatService.chat_with_tenant(phone, "vendi 3 pulseras")
        ChatService.chat_with_tenant(phone, "cuanto stock?")

    assert "[Contexto:" not in captured_inputs[1]


@pytest.mark.integration
def test_pending_marker_survives_interim_ambiguous_turn(monkeypatch):
    """Voss captura defense-in-depth: turn 1 leaves a pending price slot,
    turn 2 mis-classifies as AMBIGUOUS (no missing_fields persisted), and
    turn 3 must STILL receive the marker thanks to the look-back window.

    Reproduces the cascade documented at cp:20260508T064740Z follow-up where
    a single mis-classified turn previously dropped pending state and the
    next user message ('el precio de venta q me pediste') hit a cold
    router that hallucinated unrelated products."""
    phone = "+5491100000123"
    _mock_tenant_manager(monkeypatch, phone)

    captured_inputs: list[str] = []

    def make_invoke(payload: dict):
        def fake_invoke(state):
            captured_inputs.append(state["user_input"])
            return payload
        return fake_invoke

    fake_graph = MagicMock()

    # Turn 1: bot asks for the price of "medias planas".
    fake_graph.invoke.side_effect = make_invoke({
        "messages": [],
        "final_answer": "Me falta un dato: el precio de venta. Me lo podes decir?",
        "intent": "WRITE_OPERATION",
        "operation_type": "REGISTER_PRODUCT",
        "missing_fields": ["unit_price"],
        "normalized_entities": {"name": "medias planas"},
    })
    with patch.object(ChatService, "_get_graph", return_value=fake_graph):
        ChatService.chat_with_tenant(phone, "crear medias planas")

    # Turn 2: router mis-classifies "22 usd" as AMBIGUOUS (no missing_fields
    # to persist on this turn → previous PR-A logic dropped pending here).
    fake_graph.invoke.side_effect = make_invoke({
        "messages": [],
        "final_answer": "Es un precio, un costo, o un gasto?",
        "intent": "AMBIGUOUS",
        "operation_type": "UNKNOWN",
        "missing_fields": [],
        "normalized_entities": {},
    })
    with patch.object(ChatService, "_get_graph", return_value=fake_graph):
        ChatService.chat_with_tenant(phone, "22 usd")

    # Turn 3: user points back ("el precio de venta q me pediste"). The
    # marker MUST be rebuilt from the older turn-1 metadata.
    fake_graph.invoke.side_effect = make_invoke({
        "messages": [],
        "final_answer": "Me falta un dato: el precio de venta.",
        "intent": "WRITE_OPERATION",
        "operation_type": "REGISTER_PRODUCT",
        "missing_fields": ["unit_price"],
        "normalized_entities": {"name": "medias planas"},
    })
    with patch.object(ChatService, "_get_graph", return_value=fake_graph):
        ChatService.chat_with_tenant(phone, "el precio de venta q me pediste")

    assert len(captured_inputs) == 3
    turn3_input = captured_inputs[2]
    assert "[Contexto: turno anterior pidio el precio" in turn3_input, (
        "look-back window must rebuild the pending marker for turn 3 even "
        "though turn 2 produced no missing_fields of its own"
    )
    assert "medias planas" in turn3_input
    assert "(operacion REGISTER_PRODUCT)" in turn3_input
