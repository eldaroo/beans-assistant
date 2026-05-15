"""Tests for the write_agent navigation cue (T-007).

Contract:
- On a successful tool call (REGISTER_SALE, REGISTER_EXPENSE, etc),
  write_agent emits `state["metadata"]["navigation"] = {"tab": "..."}`.
- It NEVER emits navigation during disambiguation, missing-field bails,
  or operation failures.

These tests use the populated_db fixture so the underlying DB calls
actually commit (which is the precondition for navigation in the
contract).
"""
from __future__ import annotations

import pytest

from agents.write_agent import _navigation_for, create_write_agent
from database import add_stock


@pytest.mark.unit
class TestNavigationMap:
    @pytest.mark.parametrize(
        "op,tab",
        [
            ("REGISTER_SALE", "Ventas"),
            ("REGISTER_EXPENSE", "Gastos"),
            ("REGISTER_PRODUCT", "Productos"),
            ("REGISTER_PRODUCT_WITH_STOCK", "Productos"),
            ("UPDATE_PRODUCT_PRICE", "Productos"),
            ("ADD_STOCK", "Stock"),
            ("CANCEL_SALE", "Ventas"),
            ("CANCEL_EXPENSE", "Gastos"),
            ("CANCEL_STOCK", "Stock"),
            ("DEACTIVATE_PRODUCT", "Productos"),
        ],
    )
    def test_known_operations_map_to_tabs(self, op, tab):
        assert _navigation_for(op) == {"tab": tab}

    def test_unknown_operation_returns_none(self):
        assert _navigation_for("FOO") is None
        assert _navigation_for(None) is None

    def test_cancel_last_uses_resolved_op_type(self):
        assert _navigation_for("CANCEL_LAST_OPERATION", last_op_type="SALE") == {"tab": "Ventas"}
        assert _navigation_for("CANCEL_LAST_OPERATION", last_op_type="EXPENSE") == {"tab": "Gastos"}
        assert _navigation_for("CANCEL_LAST_OPERATION", last_op_type="STOCK") == {"tab": "Stock"}
        assert _navigation_for("CANCEL_LAST_OPERATION", last_op_type=None) is None
        assert _navigation_for("CANCEL_LAST_OPERATION", last_op_type="OTHER") is None


@pytest.mark.unit
@pytest.mark.database
class TestNavigationEmittedOnSuccess:
    def test_register_sale_success_emits_ventas(self, populated_db):
        add_stock({"product_id": 1, "quantity": 100})
        agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_SALE",
            "normalized_entities": {
                "items": [
                    {"product_id": 1, "quantity": 1, "resolved_name": "Pulsera Clásica"}
                ],
                "status": "PAID",
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION",
            "metadata": {},
        }
        result = agent(state)
        assert result.get("operation_result") is not None, "tool call should have committed"
        assert result["metadata"]["navigation"] == {"tab": "Ventas"}

    def test_register_expense_success_emits_gastos(self, populated_db):
        agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_EXPENSE",
            "normalized_entities": {
                "amount_cents": 5000,
                "description": "Insumos",
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION",
            "metadata": {},
        }
        result = agent(state)
        assert result.get("operation_result") is not None
        assert result["metadata"]["navigation"] == {"tab": "Gastos"}


@pytest.mark.unit
@pytest.mark.database
class TestNavigationNotEmittedOnFailure:
    def test_missing_fields_bail_does_not_emit(self, populated_db):
        """Disambiguation/missing-field bails MUST NOT navigate."""
        agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_SALE",
            "normalized_entities": {},
            "missing_fields": ["items"],
            "intent": "WRITE_OPERATION",
            "metadata": {},
        }
        result = agent(state)
        # Either no metadata key or no navigation entry.
        nav = (result.get("metadata") or {}).get("navigation")
        assert nav is None

    def test_validation_error_does_not_emit(self, populated_db):
        """Operation that raises during execution must not navigate."""
        agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_SALE",
            "normalized_entities": {"items": [], "status": "PAID"},
            "missing_fields": [],
            "intent": "WRITE_OPERATION",
            "metadata": {},
        }
        result = agent(state)
        # ValueError → caught by inner try, error_msg returned, no nav.
        assert result.get("error") is not None
        nav = (result.get("metadata") or {}).get("navigation")
        assert nav is None
