"""T-001: Reproduce the turn-3 typo crash from the screenshot.

The screenshot transcript at cp:20260515 shows:

    turn 1: ¿Qué productos están por agotarse?
    turn 2: agreguemos
    turn 3: un prodcuo al inventario   (typo: "prodcuo")
    bot:    No pude procesar tu mensaje ahora. (generic)

The bot response on turn 3 was the front-end's catch-all
ERROR_FALLBACK_COPY['llm_unavailable']. After M1, that turn must
produce a typed `error_code` and an `incident_id` so the operator can
correlate the failure, and the response must NOT be the generic
'llm_unavailable' copy.

This test starts as the failing target that T-002 (safe_node) +
T-003 (error_copy) + T-004 (envelope) + T-006 (Sentry tagging) turn
green. It runs end-to-end through `ChatService.chat_with_tenant` with
the LangGraph mocked: the mock simulates what the real wrapped resolver
would write into state when `un prodcuo al inventario` reaches it
(safe_node catches the resolver's "Product not found" and writes a
typed error delta).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.error_copy import compose_error_response
from backend.services.chat_service import ChatService


# Generic copy the front-end shows today via ERROR_FALLBACK_COPY['llm_unavailable'].
# Asserting that the M1 envelope NEVER returns this for the typo input is
# the whole point of T-001.
ERROR_FALLBACK_COPY_LLM_UNAVAILABLE = (
    "No pude procesar tu mensaje ahora. Probá de nuevo en un momento."
)

# The exact transcript from the screenshot, replayed turn by turn.
TURN_1_USER = "¿Qué productos están por agotarse?"
TURN_1_BOT = "No hay productos en el inventario."
TURN_2_USER = "agreguemos"
TURN_2_BOT = "¿Qué querés agregar: una venta, un gasto, un producto nuevo o stock?"
TURN_3_USER = "un prodcuo al inventario"


VALID_ERROR_CODES = {"unknown_product", "missing_field", "ambiguous_input"}


@pytest.fixture(autouse=True)
def _reset_history():
    ChatService._history_by_key.clear()
    ChatService._last_seen_by_key.clear()
    yield
    ChatService._history_by_key.clear()
    ChatService._last_seen_by_key.clear()


def _mock_tenant_manager(monkeypatch, phone: str):
    """Stub TenantManager and tenant_context the same way the existing
    integration suite does, so chat_with_tenant runs without a real DB."""
    from backend.services import chat_service as cs

    fake_manager = MagicMock()
    fake_manager.normalize_phone_number.return_value = phone
    fake_manager.resolve_tenant_phone.return_value = phone
    fake_manager.sanitize_owner_name.return_value = "Dario"
    fake_manager.set_tenant_owner_name.return_value = None
    fake_manager.get_tenant_config.return_value = {"owner_name": "Dario"}

    monkeypatch.setattr(cs, "TenantManager", lambda: fake_manager)

    from contextlib import contextmanager

    @contextmanager
    def fake_tenant_context(_phone):
        yield

    monkeypatch.setattr(cs, "tenant_context", fake_tenant_context)


@pytest.mark.unit
class TestTurn3TypoDoesNotReturnGenericCrashCopy:
    PHONE = "+5491153695627"

    def _seed_first_two_turns(self):
        """Plant turn 1 and turn 2 history so turn 3 is reproducible."""
        ChatService._append_history(
            self.PHONE,
            TURN_1_USER,
            TURN_1_BOT,
            bot_metadata={"last_intent": "READ_ANALYTICS"},
        )
        ChatService._append_history(
            self.PHONE,
            TURN_2_USER,
            TURN_2_BOT,
            bot_metadata={"last_intent": "AMBIGUOUS"},
        )

    def test_turn3_envelope_carries_typed_error_code_and_incident_id(self, monkeypatch):
        """The screenshot's turn-3 input runs through chat_with_tenant.
        The mocked graph returns the same shape safe_node would write
        when the resolver fails on a typo'd product name. The envelope
        MUST surface the typed error_code and incident_id, and MUST NOT
        emit the generic llm_unavailable copy."""
        _mock_tenant_manager(monkeypatch, self.PHONE)
        self._seed_first_two_turns()

        injected_incident = "ifc1234567"

        def fake_invoke(state):
            # safe_node would catch the resolver's "Product not found"
            # for the typo'd 'prodcuo' and write this typed error delta.
            return {
                "messages": [],
                "final_answer": None,
                "intent": "WRITE_OPERATION",
                "operation_type": "REGISTER_PRODUCT",
                "normalized_entities": {},
                "missing_fields": [],
                "error": {
                    "class": "unknown_product",
                    "node": "resolver",
                    "msg": "Product not found: prodcuo",
                    "incident_id": injected_incident,
                },
            }

        fake_graph = MagicMock()
        fake_graph.invoke.side_effect = fake_invoke

        with patch.object(ChatService, "_get_graph", return_value=fake_graph):
            envelope = ChatService.chat_with_tenant(self.PHONE, TURN_3_USER)

        # Envelope shape: dict with response + metadata.
        assert isinstance(envelope, dict)
        assert "response" in envelope
        assert "metadata" in envelope

        metadata = envelope["metadata"]

        # T-001 acceptance criteria.
        assert metadata.get("error_code") in VALID_ERROR_CODES, (
            f"error_code must be one of {VALID_ERROR_CODES}, got {metadata.get('error_code')!r}"
        )
        assert metadata.get("incident_id"), (
            "incident_id must be non-null on a typed error envelope"
        )
        assert metadata["incident_id"] == injected_incident

        # The response MUST NOT be the generic catch-all copy that the
        # front-end falls back to today.
        response = envelope["response"]
        assert ERROR_FALLBACK_COPY_LLM_UNAVAILABLE not in response, (
            f"turn 3 must not surface generic ERROR_FALLBACK_COPY copy: {response!r}"
        )

        # And the response carries the named Spanish copy with the
        # incident id substituted.
        expected_copy = compose_error_response("unknown_product", injected_incident)
        assert response == expected_copy

    def test_turn3_response_is_actionable_spanish(self, monkeypatch):
        """Loose smoke check on the user-facing string itself."""
        _mock_tenant_manager(monkeypatch, self.PHONE)
        self._seed_first_two_turns()

        def fake_invoke(state):
            return {
                "messages": [],
                "final_answer": None,
                "intent": "WRITE_OPERATION",
                "operation_type": "REGISTER_PRODUCT",
                "normalized_entities": {},
                "missing_fields": [],
                "error": {
                    "class": "unknown_product",
                    "node": "resolver",
                    "msg": "Product not found: prodcuo",
                    "incident_id": "abcd123456",
                },
            }

        fake_graph = MagicMock()
        fake_graph.invoke.side_effect = fake_invoke

        with patch.object(ChatService, "_get_graph", return_value=fake_graph):
            envelope = ChatService.chat_with_tenant(self.PHONE, TURN_3_USER)

        response = envelope["response"]
        assert "incidente abcd123456" in response
        # No emojis or exclamations leaking through (voice rule).
        for forbidden in ("—", "–", "!", "🚀", "✨", "❌"):
            assert forbidden not in response

    def test_turn3_navigation_is_none_on_error(self, monkeypatch):
        """Errors must NOT trigger UI navigation. The widget should keep
        the user where they are."""
        _mock_tenant_manager(monkeypatch, self.PHONE)
        self._seed_first_two_turns()

        def fake_invoke(state):
            return {
                "messages": [],
                "final_answer": None,
                "intent": "WRITE_OPERATION",
                "operation_type": "REGISTER_PRODUCT",
                "normalized_entities": {},
                "missing_fields": [],
                "error": {
                    "class": "unknown_product",
                    "node": "resolver",
                    "msg": "Product not found",
                    "incident_id": "xyz0000000",
                },
            }

        fake_graph = MagicMock()
        fake_graph.invoke.side_effect = fake_invoke

        with patch.object(ChatService, "_get_graph", return_value=fake_graph):
            envelope = ChatService.chat_with_tenant(self.PHONE, TURN_3_USER)

        assert envelope["metadata"].get("navigation") is None
