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


@pytest.mark.unit
class TestPendingEntitiesMetadata:
    """PR-A fix #3: cross-turn missing-fields context.

    When the previous assistant turn finished with missing_fields, the
    next turn router needs to know which named products are still
    waiting on data. Without this, "las medias 15" reaches the router
    cold and the bot loses the binding to the products from turn 1.
    """
    PHONE = "+5491153695627"

    def test_build_pending_entities_single_product(self):
        result = ChatService._build_pending_entities(
            operation_type="REGISTER_PRODUCT",
            normalized_entities={"name": "medias", "sku": "MEDIAS"},
            missing_fields=["unit_price_cents"],
        )
        assert result == {
            "operation_type": "REGISTER_PRODUCT",
            "items": [
                {"name": "medias", "missing_fields": ["unit_price_cents"]},
            ],
        }

    def test_build_pending_entities_items_list(self):
        result = ChatService._build_pending_entities(
            operation_type="REGISTER_PRODUCT",
            normalized_entities={
                "items": [
                    {"name": "medias"},
                    {"name": "pantaletas"},
                ],
            },
            missing_fields=["unit_price_cents"],
        )
        assert result["operation_type"] == "REGISTER_PRODUCT"
        names = [item["name"] for item in result["items"]]
        assert names == ["medias", "pantaletas"]
        for item in result["items"]:
            assert item["missing_fields"] == ["unit_price_cents"]

    def test_build_pending_entities_empty_missing_fields_returns_none(self):
        result = ChatService._build_pending_entities(
            operation_type="REGISTER_PRODUCT",
            normalized_entities={"name": "medias"},
            missing_fields=[],
        )
        assert result is None

    def test_build_pending_entities_no_named_items_returns_none(self):
        result = ChatService._build_pending_entities(
            operation_type="REGISTER_PRODUCT",
            normalized_entities={},
            missing_fields=["name"],
        )
        assert result is None

    def test_build_pending_entities_skips_marker_only(self):
        """If the only missing field is the comma-name marker (PR-A fix #1),
        treat as nothing real to chase across turns."""
        result = ChatService._build_pending_entities(
            operation_type="REGISTER_PRODUCT",
            normalized_entities={"name": "medias, pantaletas"},
            missing_fields=["ambiguous_comma_name_split"],
        )
        assert result is None

    def test_pending_entities_persisted_when_missing_fields_present(self):
        """The full _append_history flow records pending_entities."""
        ChatService._append_history(
            self.PHONE,
            "vendo medias",
            "Me falta un dato: el precio de venta",
            bot_metadata={
                "last_intent": "WRITE_OPERATION",
                "operation_type": "REGISTER_PRODUCT",
                "pending_entities": {
                    "operation_type": "REGISTER_PRODUCT",
                    "items": [
                        {"name": "medias", "missing_fields": ["unit_price_cents"]},
                    ],
                },
            },
        )
        history = ChatService._history_by_key[ChatService._history_key(self.PHONE)]
        assistant_entry = next(e for e in history if e.get("role") == "assistant")

        assert "pending_entities" in assistant_entry["metadata"]
        assert assistant_entry["metadata"]["pending_entities"]["items"][0]["name"] == "medias"

    def test_pending_entities_cleared_when_resolved(self):
        """Turn N had pending_entities; turn N+1 resolves all (no missing
        fields). The N+1 entry must NOT carry pending_entities forward.
        Cleanup happens because the caller only passes pending_entities
        when the current turn still has missing_fields."""
        ChatService._append_history(
            self.PHONE,
            "vendo medias",
            "Me falta el precio",
            bot_metadata={
                "last_intent": "WRITE_OPERATION",
                "operation_type": "REGISTER_PRODUCT",
                "pending_entities": {
                    "operation_type": "REGISTER_PRODUCT",
                    "items": [
                        {"name": "medias", "missing_fields": ["unit_price_cents"]},
                    ],
                },
            },
        )
        ChatService._append_history(
            self.PHONE,
            "las medias 15",
            "Listo, cargué medias a $15.",
            bot_metadata={
                "last_intent": "WRITE_OPERATION",
                "operation_type": "REGISTER_PRODUCT",
                "pending_entities": None,
            },
        )

        history = ChatService._history_by_key[ChatService._history_key(self.PHONE)]
        assistant_entries = [e for e in history if e.get("role") == "assistant"]
        latest = assistant_entries[-1]
        assert "pending_entities" not in (latest.get("metadata") or {})

    def test_pending_marker_injected_in_message_with_context(self):
        """Turn N+1 router sees the [Contexto:...] marker."""
        ChatService._append_history(
            self.PHONE,
            "vendo medias, pantaletas y soquetes",
            "Me falta un dato: el precio de venta",
            bot_metadata={
                "last_intent": "WRITE_OPERATION",
                "operation_type": "REGISTER_PRODUCT",
                "pending_entities": {
                    "operation_type": "REGISTER_PRODUCT",
                    "items": [
                        {"name": "medias", "missing_fields": ["unit_price_cents"]},
                        {"name": "pantaletas", "missing_fields": ["unit_price_cents"]},
                        {"name": "soquetes", "missing_fields": ["unit_price_cents"]},
                    ],
                },
            },
        )
        msg = ChatService._build_message_with_context(
            self.PHONE,
            "las medias 15, las pantaletas 20",
        )
        assert "[Contexto: turno anterior pidio el precio" in msg
        assert "medias" in msg
        assert "pantaletas" in msg
        assert "soquetes" in msg
        assert "Mensaje actual: las medias 15, las pantaletas 20" in msg

    def test_no_pending_marker_when_last_assistant_has_no_pending(self):
        """When pending_entities was cleared, the [Contexto:...] marker
        must not appear in the next router input."""
        ChatService._append_history(
            self.PHONE,
            "vendi 3 pulseras",
            "Venta registrada!",
            bot_metadata={
                "last_intent": "WRITE_OPERATION",
                "operation_type": "REGISTER_SALE",
            },
        )
        msg = ChatService._build_message_with_context(self.PHONE, "cuanto stock?")
        assert "[Contexto:" not in msg
