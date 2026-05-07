"""Tests for the ambiguity-context bridge in ChatService.

When the previous assistant turn left the conversation in an AMBIGUOUS
disambiguation state (the bot asked which of two intents the user
meant), the next turn must include a marker so the router reads the
user's reply as the disambiguation answer instead of re-classifying
cold.
"""
import pytest

from backend.services.chat_service import ChatService


@pytest.fixture(autouse=True)
def _reset_history():
    """Each test starts with an empty in-process history dict."""
    ChatService._history_by_key.clear()
    ChatService._last_seen_by_key.clear()
    yield
    ChatService._history_by_key.clear()
    ChatService._last_seen_by_key.clear()


@pytest.mark.unit
class TestAmbiguityMarkerInjection:
    PHONE = "+5491153695627"

    def test_no_marker_when_history_empty(self):
        msg = ChatService._build_message_with_context(self.PHONE, "hola")
        assert msg == "hola"
        assert "Nota:" not in msg

    def test_no_marker_when_last_intent_was_not_ambiguous(self):
        ChatService._append_history(
            self.PHONE,
            "vendi 3 pulseras",
            "Venta registrada!",
            bot_metadata={"last_intent": "WRITE_OPERATION", "operation_type": "REGISTER_SALE"},
        )
        msg = ChatService._build_message_with_context(self.PHONE, "cuanto stock me queda?")

        assert "Nota:" not in msg
        assert "Mensaje actual: cuanto stock me queda?" in msg

    def test_marker_injected_when_last_intent_was_ambiguous(self):
        """Reproduces the Dario chat flow at the conversation-state seam."""
        ChatService._append_history(
            self.PHONE,
            "me agregarias unos productos a mi inventario?",
            "Querés crear productos nuevos en tu catálogo, o sumar stock a productos que ya tenés?",
            bot_metadata={"last_intent": "AMBIGUOUS"},
        )
        msg = ChatService._build_message_with_context(
            self.PHONE,
            "Peras verdes son, y la cantidad 22",
        )

        assert "[Nota: el turno anterior del asistente fue una pregunta de aclaracion" in msg
        assert "Mensaje actual: Peras verdes son, y la cantidad 22" in msg
        # The original context lines must still be there.
        assert "Querés crear productos nuevos" in msg

    def test_metadata_persists_across_appends(self):
        """The metadata field on assistant entries survives the deque append."""
        ChatService._append_history(
            self.PHONE,
            "u1",
            "a1",
            bot_metadata={"last_intent": "AMBIGUOUS", "operation_type": "UNKNOWN"},
        )
        history = ChatService._history_by_key[ChatService._history_key(self.PHONE)]
        assistant_entry = next(e for e in history if e.get("role") == "assistant")

        assert assistant_entry["metadata"] == {
            "last_intent": "AMBIGUOUS",
            "operation_type": "UNKNOWN",
        }

    def test_metadata_only_keeps_lean_shape(self):
        """The persisted metadata must drop noisy keys like confidence so
        the in-memory store stays small and predictable."""
        ChatService._append_history(
            self.PHONE,
            "u",
            "a",
            bot_metadata={
                "last_intent": "AMBIGUOUS",
                "operation_type": "UNKNOWN",
                "confidence": 0.92,
                "extra_garbage": "ignore me",
            },
        )
        history = ChatService._history_by_key[ChatService._history_key(self.PHONE)]
        assistant_entry = next(e for e in history if e.get("role") == "assistant")

        assert "confidence" not in assistant_entry["metadata"]
        assert "extra_garbage" not in assistant_entry["metadata"]
