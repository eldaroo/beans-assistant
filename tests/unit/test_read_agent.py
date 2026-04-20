"""Unit tests for agents/read_agent.py formatting helpers."""
import pytest

import agents.read_agent as read_agent
from agents.read_agent import format_stock_result, generate_sales_query


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


@pytest.mark.unit
class TestGenerateSalesQuery:
    """Tests for sales history SQL generation."""

    def test_generate_sales_query_uses_postgres_aggregation_when_enabled(self, monkeypatch):
        """PostgreSQL mode should not emit MySQL-only GROUP_CONCAT."""
        monkeypatch.setattr(read_agent, "USE_POSTGRES", True)

        sql = generate_sales_query({})

        assert "STRING_AGG" in sql
        assert "GROUP_CONCAT" not in sql

    def test_generate_sales_query_uses_sqlite_aggregation_when_disabled(self, monkeypatch):
        """SQLite mode should keep using GROUP_CONCAT."""
        monkeypatch.setattr(read_agent, "USE_POSTGRES", False)

        sql = generate_sales_query({})

        assert "GROUP_CONCAT" in sql
        assert "STRING_AGG" not in sql
