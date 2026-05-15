"""Tests for the named-Spanish error copy module (T-003).

Each of the five error classes resolves to its documented Spanish line
with the incident id substituted into the trailing parenthetical. Voice
rules (no em-dashes, no exclamations, no emojis, no hype words) are
asserted on every rendered line.
"""
from __future__ import annotations

import pytest

from agents.error_copy import compose_error_response, supported_classes


_INCIDENT = "abc1234567"

# Voice rules from CLAUDE memory: no em-dashes, no en-dashes, no
# exclamations, no emojis, no hype words. We assert the deterministic
# subset here.
_FORBIDDEN_CHARS = ("—", "–", "!", "🚀", "✨", "🔥", "✅", "❌")


@pytest.mark.unit
class TestSupportedClasses:
    def test_exactly_five_classes(self):
        classes = set(supported_classes())
        assert classes == {
            "unknown_product",
            "missing_field",
            "network",
            "llm_unavailable",
            "ambiguous_input",
        }


@pytest.mark.unit
class TestComposeErrorResponse:
    @pytest.mark.parametrize("error_class", list(supported_classes()))
    def test_each_class_substitutes_incident_id(self, error_class):
        line = compose_error_response(error_class, _INCIDENT)
        assert _INCIDENT in line
        assert f"(incidente {_INCIDENT})" in line

    @pytest.mark.parametrize("error_class", list(supported_classes()))
    def test_each_class_obeys_voice_rules(self, error_class):
        line = compose_error_response(error_class, _INCIDENT)
        for forbidden in _FORBIDDEN_CHARS:
            assert forbidden not in line, (
                f"{error_class!r} copy contains forbidden char {forbidden!r}: {line!r}"
            )

    def test_unknown_product_copy(self):
        line = compose_error_response("unknown_product", _INCIDENT)
        assert "No reconocí el producto" in line

    def test_missing_field_default_hint(self):
        line = compose_error_response("missing_field", _INCIDENT)
        assert "Me falta un dato" in line
        assert "el detalle que me faltó" in line

    def test_missing_field_custom_hint(self):
        line = compose_error_response(
            "missing_field", _INCIDENT, hint="el precio de venta"
        )
        assert "el precio de venta" in line
        assert "el detalle que me faltó" not in line

    def test_network_copy(self):
        line = compose_error_response("network", _INCIDENT)
        assert "problema técnico" in line
        assert "Probá de nuevo" in line

    def test_llm_unavailable_copy(self):
        line = compose_error_response("llm_unavailable", _INCIDENT)
        assert "El asistente no pudo responder" in line

    def test_ambiguous_input_kaze_recovery(self):
        line = compose_error_response("ambiguous_input", _INCIDENT)
        assert "Eso no me salió" in line
        assert "Volvamos a lo de los productos" in line

    def test_unknown_class_falls_back_to_llm_unavailable(self):
        line = compose_error_response("totally_unknown", _INCIDENT)
        assert "El asistente no pudo responder" in line
        assert _INCIDENT in line
