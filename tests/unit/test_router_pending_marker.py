"""Unit tests for the deterministic pending-slot marker short-circuit.

The router's prompt is unable to reliably honor the
[Contexto: turno anterior pidio ...] marker under noisy multi-turn
conversation history (Gemini-flash falls back to AMBIGUOUS clarifiers).
These tests pin the deterministic parser that bypasses the LLM whenever
the marker is present, reproducing the Voss captura
(cp:20260508T064740Z follow-up).
"""
from __future__ import annotations

import pytest

from agents.router import (
    _parse_pending_marker,
    _short_circuit_pending_marker,
)


class TestParsePendingMarker:
    def test_marker_with_price_and_register_product(self):
        text = (
            "Contexto de conversación reciente:\n"
            "Usuario: x\n"
            "Asistente: y\n\n"
            "[Contexto: turno anterior pidio el precio para los productos: "
            "medias planas (operacion REGISTER_PRODUCT). El usuario ahora "
            "puede estar respondiendo con esos datos.]\n"
            "Mensaje actual: 22 usd"
        )
        out = _parse_pending_marker(text)
        assert out is not None
        assert out["field_label"] == "el precio"
        assert out["names_raw"] == "medias planas"
        assert out["operation_type"] == "REGISTER_PRODUCT"
        assert out["user_reply"] == "22 usd"

    def test_no_marker_returns_none(self):
        assert _parse_pending_marker("vendi 3 manzanas") is None
        assert _parse_pending_marker("") is None
        assert _parse_pending_marker(None) is None

    def test_marker_with_quantity(self):
        text = (
            "[Contexto: turno anterior pidio la cantidad para los "
            "productos: pulseras (operacion ADD_STOCK). ...]\n"
            "Mensaje actual: 50"
        )
        out = _parse_pending_marker(text)
        assert out is not None
        assert out["field_label"] == "la cantidad"
        assert out["operation_type"] == "ADD_STOCK"
        assert out["user_reply"] == "50"


class TestShortCircuitPendingMarker:
    def test_voss_captura_bare_price(self):
        """Captura turn 5: bot asked price for medias planas, user said
        '22 usd'. Must emit REGISTER_PRODUCT with unit_price=22."""
        text = (
            "Contexto de conversación reciente:\n"
            "Usuario: un producto nuevo\n"
            "Asistente: Me falta un dato: *el nombre del producto*\n"
            "Usuario: el product se llama medias planas\n"
            "Asistente: Me falta un dato: *el precio de venta*\n\n"
            "[Contexto: turno anterior pidio el precio para los productos: "
            "medias planas (operacion REGISTER_PRODUCT). El usuario ahora "
            "puede estar respondiendo con esos datos.]\n"
            "Mensaje actual: 22 usd"
        )
        out = _short_circuit_pending_marker(text)
        assert out is not None
        assert out["intent"] == "WRITE_OPERATION"
        assert out["operation_type"] == "REGISTER_PRODUCT"
        assert out["normalized_entities"] == {
            "name": "medias planas",
            "unit_price": 22,
        }
        assert out["missing_fields"] == []

    @pytest.mark.parametrize(
        "reply,expected_value",
        [
            ("22 usd", 22),
            ("22", 22),
            ("$22", 22),
            ("a 22", 22),
            ("22 dolares", 22),
            ("22 dólares", 22),
            ("22.50 usd", 22.5),
            ("1500", 1500),
        ],
    )
    def test_numeric_price_variants(self, reply, expected_value):
        text = (
            "[Contexto: turno anterior pidio el precio para los productos: "
            "x (operacion REGISTER_PRODUCT). ...]\n"
            f"Mensaje actual: {reply}"
        )
        out = _short_circuit_pending_marker(text)
        assert out is not None
        assert out["normalized_entities"]["unit_price"] == expected_value
        assert out["missing_fields"] == []

    def test_user_pointer_back_keeps_slot_open(self):
        """Captura turn 6: user said 'el precio de venta q me pediste' (no
        number). Must NOT invent products, must NOT emit AMBIGUOUS, must
        keep unit_price as missing under REGISTER_PRODUCT."""
        text = (
            "[Contexto: turno anterior pidio el precio para los productos: "
            "medias planas (operacion REGISTER_PRODUCT). ...]\n"
            "Mensaje actual: el precio de venta q me pediste"
        )
        out = _short_circuit_pending_marker(text)
        assert out is not None
        assert out["intent"] == "WRITE_OPERATION"
        assert out["operation_type"] == "REGISTER_PRODUCT"
        assert out["normalized_entities"] == {"name": "medias planas"}
        assert out["missing_fields"] == ["unit_price"]

    def test_no_marker_falls_through(self):
        """Without the marker, short-circuit returns None and the LLM
        path runs as before."""
        assert _short_circuit_pending_marker("vendi 3 pulseras") is None
        assert _short_circuit_pending_marker("Mensaje actual: 22 usd") is None

    def test_short_name_reply_for_pending_name(self):
        text = (
            "[Contexto: turno anterior pidio el nombre para los productos: "
            "los productos previos (operacion REGISTER_PRODUCT). ...]\n"
            "Mensaje actual: pulseras de cuero"
        )
        out = _short_circuit_pending_marker(text)
        assert out is not None
        assert out["operation_type"] == "REGISTER_PRODUCT"
        assert out["normalized_entities"]["name"] == "pulseras de cuero"

    def test_long_name_reply_falls_through_to_llm(self):
        """A long descriptive sentence ('el producto se llama X y hace
        referencia a ...') needs LLM extraction. Short-circuit defers."""
        text = (
            "[Contexto: turno anterior pidio el nombre para los productos: "
            "los productos previos (operacion REGISTER_PRODUCT). ...]\n"
            "Mensaje actual: el producto se llama medias planas y hace "
            "referencia a las medias que no tienen dibujo"
        )
        assert _short_circuit_pending_marker(text) is None

    def test_unknown_field_falls_through(self):
        """An unrecognized Spanish field label defers to the LLM."""
        text = (
            "[Contexto: turno anterior pidio el sabor para los productos: "
            "x (operacion REGISTER_PRODUCT). ...]\n"
            "Mensaje actual: vainilla"
        )
        assert _short_circuit_pending_marker(text) is None
