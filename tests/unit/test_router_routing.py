"""
Tests for router routing function and DECLINE_PRODUCT_CREATION final-answer
handling. These do not exercise the LLM classification; the router prompt
itself is exercised in `tests/eval/router_propose_confirm.json`.
"""
import pytest

from agents.router import route_to_next_node


@pytest.mark.unit
class TestRouteToNextNode:
    """Routing decisions based on the router state."""

    def test_greeting_goes_to_final_answer(self):
        state = {"intent": "GREETING"}
        assert route_to_next_node(state) == "final_answer"

    def test_decline_product_creation_goes_to_final_answer(self):
        state = {"intent": "DECLINE_PRODUCT_CREATION"}
        assert route_to_next_node(state) == "final_answer"

    def test_ambiguous_goes_to_final_answer(self):
        state = {"intent": "AMBIGUOUS"}
        assert route_to_next_node(state) == "final_answer"

    def test_missing_fields_goes_to_final_answer(self):
        state = {"intent": "WRITE_OPERATION", "missing_fields": ["quantity"]}
        assert route_to_next_node(state) == "final_answer"

    def test_read_analytics_goes_to_read_agent(self):
        state = {"intent": "READ_ANALYTICS"}
        assert route_to_next_node(state) == "read_agent"

    def test_write_operation_goes_to_resolver(self):
        state = {"intent": "WRITE_OPERATION", "missing_fields": []}
        assert route_to_next_node(state) == "resolver"

    def test_register_product_with_stock_goes_to_resolver(self):
        """The new compound op must still flow router -> resolver -> write_agent."""
        state = {
            "intent": "WRITE_OPERATION",
            "operation_type": "REGISTER_PRODUCT_WITH_STOCK",
            "missing_fields": [],
        }
        assert route_to_next_node(state) == "resolver"

    def test_mixed_goes_to_resolver(self):
        state = {"intent": "MIXED", "missing_fields": []}
        assert route_to_next_node(state) == "resolver"

    def test_error_goes_to_final_answer(self):
        state = {"intent": "WRITE_OPERATION", "error": "boom"}
        assert route_to_next_node(state) == "final_answer"


@pytest.mark.unit
class TestFinalAnswerDeclineBranch:
    """The final_answer node must produce the ack-and-forget message."""

    def _node(self):
        from graph import create_final_answer_node
        return create_final_answer_node()

    def test_decline_uses_candidate_name(self):
        node = self._node()
        state = {
            "intent": "DECLINE_PRODUCT_CREATION",
            "normalized_entities": {"candidate_name": "manzanas"},
        }
        result = node(state)
        msg = result["final_answer"]
        assert "Ok" in msg
        assert "manzanas" in msg
        assert "No registro" in msg
        # No filtra product_id u otros nombres internos
        assert "product_id" not in msg
        assert "candidate_name" not in msg

    def test_decline_without_candidate_falls_back_gracefully(self):
        node = self._node()
        state = {
            "intent": "DECLINE_PRODUCT_CREATION",
            "normalized_entities": {},
        }
        result = node(state)
        msg = result["final_answer"]
        assert "el producto" in msg
        assert "Ok" in msg
