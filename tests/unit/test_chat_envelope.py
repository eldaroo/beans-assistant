"""Tests for the public chat envelope (T-004).

`ChatService.chat_with_tenant` now returns a dict shaped:

    {
        "response": str,
        "metadata": {
            "error_code": Optional[str],
            "incident_id": Optional[str],
            "navigation": Optional[dict],
            ...
        },
    }

These tests exercise the envelope assembly logic via
`ChatService._build_envelope` so they stay fast and don't require the
real graph or LLMs. Integration coverage for the full path lives under
`tests/integration/`.
"""
from __future__ import annotations

import pytest

from agents.error_copy import compose_error_response
from backend.services.chat_service import ChatService


@pytest.mark.unit
class TestBuildEnvelopeCleanPath:
    def test_returns_response_and_null_error_fields(self):
        envelope = ChatService._build_envelope(
            {"error": None, "metadata": {"intent": "READ_ANALYTICS"}},
            fallback_response="Hola",
        )
        assert envelope["response"] == "Hola"
        assert envelope["metadata"]["error_code"] is None
        assert envelope["metadata"]["incident_id"] is None
        assert envelope["metadata"]["navigation"] is None
        # Existing graph metadata pass-through.
        assert envelope["metadata"]["intent"] == "READ_ANALYTICS"

    def test_navigation_passthrough(self):
        envelope = ChatService._build_envelope(
            {
                "error": None,
                "metadata": {"navigation": {"tab": "Ventas"}},
            },
            fallback_response="Listo, cargué la venta.",
        )
        assert envelope["metadata"]["navigation"] == {"tab": "Ventas"}
        assert envelope["metadata"]["error_code"] is None


@pytest.mark.unit
class TestBuildEnvelopeErrorPath:
    def test_replaces_response_with_named_spanish_copy(self):
        incident_id = "abcdef0123"
        envelope = ChatService._build_envelope(
            {
                "error": {
                    "class": "unknown_product",
                    "node": "resolver",
                    "msg": "Product not found",
                    "incident_id": incident_id,
                },
                "metadata": {"intent": "WRITE_OPERATION"},
            },
            fallback_response="should be ignored",
        )
        expected_copy = compose_error_response("unknown_product", incident_id)
        assert envelope["response"] == expected_copy
        assert envelope["metadata"]["error_code"] == "unknown_product"
        assert envelope["metadata"]["incident_id"] == incident_id

    @pytest.mark.parametrize(
        "error_class",
        ["unknown_product", "missing_field", "network", "llm_unavailable", "ambiguous_input"],
    )
    def test_each_supported_class_surfaces(self, error_class):
        envelope = ChatService._build_envelope(
            {
                "error": {
                    "class": error_class,
                    "node": "router",
                    "msg": "boom",
                    "incident_id": "1234567890",
                },
                "metadata": {},
            },
            fallback_response="ignored",
        )
        assert envelope["metadata"]["error_code"] == error_class
        assert envelope["metadata"]["incident_id"] == "1234567890"
        # The response should contain the incident id parenthetical so the
        # operator can correlate the user's report with the log line.
        assert "1234567890" in envelope["response"]

    def test_unknown_class_falls_back_to_clean_path(self):
        """If a node writes an error with a class we don't know, we don't
        invent a code; we surface the raw response and let the operator
        debug from the structured log line."""
        envelope = ChatService._build_envelope(
            {
                "error": {
                    "class": "totally_unknown",
                    "node": "router",
                    "msg": "?",
                    "incident_id": "x",
                },
                "metadata": {},
            },
            fallback_response="raw response",
        )
        assert envelope["response"] == "raw response"
        assert envelope["metadata"]["error_code"] is None
        assert envelope["metadata"]["incident_id"] is None

    def test_string_error_legacy_does_not_crash(self):
        """Older write_agent paths still set state.error to a string.
        Envelope must not crash; it falls back to the clean path so the
        existing copy from final_answer surfaces unchanged."""
        envelope = ChatService._build_envelope(
            {"error": "Operación fallida: legacy string", "metadata": {}},
            fallback_response="Operación fallida: legacy string",
        )
        assert envelope["response"] == "Operación fallida: legacy string"
        assert envelope["metadata"]["error_code"] is None


@pytest.mark.unit
class TestEnvelopeMetadataKeys:
    def test_required_keys_always_present(self):
        envelope = ChatService._build_envelope(
            {"error": None, "metadata": {}},
            fallback_response="x",
        )
        for key in ("error_code", "incident_id", "navigation"):
            assert key in envelope["metadata"], f"missing {key} from envelope metadata"

    def test_envelope_keys_are_response_and_metadata(self):
        envelope = ChatService._build_envelope(
            {"error": None, "metadata": {}},
            fallback_response="x",
        )
        assert set(envelope.keys()) == {"response", "metadata"}
