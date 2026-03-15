"""Unit tests for agents/read_agent.py formatting helpers."""
import pytest

from agents.read_agent import format_stock_result


@pytest.mark.unit
class TestFormatStockResult:
    """Tests for stock result formatting."""

    def test_format_stock_result_includes_all_products(self):
        """It should not hide non-bracelet products in all-stock responses."""
        rows = [
            {"name": "pulseras azules", "stock_qty": 15},
            {"name": "pulseras rojas", "stock_qty": 32},
            {"name": "collares persas", "stock_qty": 100},
        ]

        result = format_stock_result(rows)

        assert "pulseras azules" in result
        assert "pulseras rojas" in result
        assert "collares persas" in result

    def test_format_stock_result_handles_empty_rows(self):
        """It should return a friendly empty-state message."""
        assert format_stock_result([]) == "No hay productos en el inventario."
