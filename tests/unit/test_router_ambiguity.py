"""Tests for the AMBIGUOUS clarifier path in the router.

The router prompt itself (the LLM call) is exercised via the eval set
`tests/eval/router_ambiguity.json`. The unit tests below cover the
deterministic Python wrapper `classification_to_state`: when the LLM
returns AMBIGUOUS with a clarifier, the wrapper must surface the
clarifier as `final_answer` so the graph short-circuits straight to
the user.
"""
import pytest

from agents.router import classification_to_state


@pytest.mark.unit
class TestClassificationToState:
    def test_ambiguous_high_confidence_uses_clarifier_as_final_answer(self):
        state = classification_to_state({
            "intent": "AMBIGUOUS",
            "operation_type": "UNKNOWN",
            "confidence": 0.92,
            "missing_fields": [],
            "normalized_entities": {},
            "reasoning": "User said 'agregar productos'",
            "clarifier": "Querés crear productos nuevos o sumar stock?",
        })

        assert state["intent"] == "AMBIGUOUS"
        assert state["final_answer"] == "Querés crear productos nuevos o sumar stock?"

    def test_ambiguous_without_clarifier_falls_back_to_generic(self):
        """If the LLM forgets to fill clarifier, we still emit something
        rather than route silently to the resolver."""
        state = classification_to_state({
            "intent": "AMBIGUOUS",
            "operation_type": "UNKNOWN",
            "confidence": 0.85,
            "missing_fields": [],
            "normalized_entities": {},
            "reasoning": "No idea",
            "clarifier": None,
        })

        assert state["intent"] == "AMBIGUOUS"
        assert state["final_answer"]
        assert "ambiguo" in state["final_answer"].lower()

    def test_low_confidence_takes_precedence_over_intent_label(self):
        """confidence < 0.6 forces the legacy clarification regardless of
        intent label, so we don't change behavior for the historical case
        where the LLM was shaky."""
        state = classification_to_state({
            "intent": "WRITE_OPERATION",
            "operation_type": "REGISTER_SALE",
            "confidence": 0.4,
            "missing_fields": [],
            "normalized_entities": {},
            "reasoning": "Shaky",
        })

        assert state["intent"] == "AMBIGUOUS"
        assert "consultar datos" in state["final_answer"]

    def test_non_ambiguous_does_not_set_final_answer(self):
        """Confident WRITE_OPERATION must flow to resolver, not short-circuit."""
        state = classification_to_state({
            "intent": "WRITE_OPERATION",
            "operation_type": "ADD_STOCK",
            "confidence": 0.9,
            "missing_fields": [],
            "normalized_entities": {"product_ref": "pulseras", "quantity": 10},
            "reasoning": "Clear ADD_STOCK",
        })

        assert state["intent"] == "WRITE_OPERATION"
        assert "final_answer" not in state

    def test_register_product_with_stock_passes_through(self):
        """The compound op stays as WRITE_OPERATION; routing to resolver
        is the resolver's job."""
        state = classification_to_state({
            "intent": "WRITE_OPERATION",
            "operation_type": "REGISTER_PRODUCT_WITH_STOCK",
            "confidence": 0.92,
            "missing_fields": [],
            "normalized_entities": {"name": "manzanas", "initial_stock": 15},
            "reasoning": "User confirmed proposed creation",
        })

        assert state["intent"] == "WRITE_OPERATION"
        assert state["operation_type"] == "REGISTER_PRODUCT_WITH_STOCK"
        assert "final_answer" not in state
