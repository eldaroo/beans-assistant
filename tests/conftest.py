"""
Shared pytest fixtures for all tests.

Fixtures provided:
- test_db: Isolated SQLite database with full schema
- populated_db: Database pre-populated with sample products
- product_builder: Factory for creating product test data
- sale_builder: Factory for creating sale test data
- expense_builder: Factory for creating expense test data
"""
import pytest
import sqlite3
import database
from pathlib import Path


@pytest.fixture(autouse=False)
def test_db(tmp_path, monkeypatch):
    """
    Create isolated test database with full schema.

    Uses:
    - tmp_path: Temporary directory for DB file (auto-cleanup)
    - monkeypatch: Patch database.get_conn() to use test DB

    Yields:
        Path to test database file
    """
    db_file = tmp_path / "test_beansco.db"

    # Read schema from init_complete_database.sql
    schema_path = Path(__file__).parent.parent / "init_complete_database.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Create database with full schema
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()

    # Patch get_conn to use test database
    from contextlib import contextmanager

    @contextmanager
    def test_get_conn():
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    monkeypatch.setattr("database.get_conn", test_get_conn)

    yield db_file

    # Cleanup happens automatically (tmp_path is deleted after test)


@pytest.fixture
def populated_db(test_db):
    """
    Database with sample products adjusted for testing.

    The schema includes products, but we update them to have consistent test values:
    - BC-BRACELET-CLASSIC: $35 sale, $12 cost
    - BC-BRACELET-BLACK: $35 sale, $12 cost
    - BC-BRACELET-GOLD: $35 sale, $12 cost
    - BC-KEYCHAIN: $20 sale, $8 cost
    """
    # Update product prices to match test expectations
    with database.get_conn() as conn:
        conn.execute("UPDATE products SET unit_price_cents = 3500, unit_cost_cents = 1200 WHERE sku LIKE 'BC-BRACELET-%'")
        conn.execute("UPDATE products SET unit_price_cents = 2000, unit_cost_cents = 800 WHERE sku = 'BC-KEYCHAIN'")
        # Clear any existing stock movements from schema
        conn.execute("DELETE FROM stock_movements")
        # Clear any existing sales from schema
        conn.execute("DELETE FROM sale_items")
        conn.execute("DELETE FROM sales")
        # Clear any existing expenses from schema
        conn.execute("DELETE FROM expenses")

    yield test_db


# ==============================================================================
# DATA BUILDER FIXTURES
# ==============================================================================

@pytest.fixture
def product_builder():
    """
    Factory for creating product test data with defaults.

    Usage:
        product_data = product_builder.build(name="Custom Product", unit_price_cents=5000)
        database.register_product(product_data)
    """
    class ProductBuilder:
        def build(self, **overrides):
            """Build product data dict with defaults and overrides."""
            defaults = {
                "sku": "TEST-PRODUCT",
                "name": "Test Product",
                "description": "Test product description",
                "unit_price_cents": 1000,  # $10
                "unit_cost_cents": 500,    # $5
            }
            return {**defaults, **overrides}

    return ProductBuilder()


@pytest.fixture
def sale_builder():
    """
    Factory for creating sale test data with defaults.

    Usage:
        sale_data = sale_builder.build(items=[{"product_id": 1, "quantity": 5}])
        database.register_sale(sale_data)
    """
    class SaleBuilder:
        def build(self, **overrides):
            """Build sale data dict with defaults and overrides."""
            defaults = {
                "status": "PAID",
                "items": [
                    {"product_id": 1, "quantity": 1}
                ]
            }
            return {**defaults, **overrides}

    return SaleBuilder()


@pytest.fixture
def expense_builder():
    """
    Factory for creating expense test data with defaults.

    Usage:
        expense_data = expense_builder.build(amount_cents=5000, description="Test expense")
        database.register_expense(expense_data)
    """
    class ExpenseBuilder:
        def build(self, **overrides):
            """Build expense data dict with defaults and overrides."""
            defaults = {
                "amount_cents": 1000,  # $10
                "description": "Test Expense",
                "category": "GENERAL",
            }
            return {**defaults, **overrides}

    return ExpenseBuilder()


@pytest.fixture
def mock_llm():
    """
    Mock LLM for testing disambiguation without API calls.

    Returns a mock that simulates LLM behavior for product disambiguation.
    """
    from unittest.mock import Mock, MagicMock
    import json
    import re

    # Create a mock AIMessage class that Langchain expects
    class MockAIMessage:
        def __init__(self, content_str):
            self.content = content_str  # Must be a string (JSON)

    # Create mock LLM
    llm = Mock()

    # Track invocations
    llm.invocations = []

    # Mock invoke method - this is what gets called after prompt formatting
    def mock_llm_invoke(prompt_value):
        # Extract the formatted prompt
        if hasattr(prompt_value, 'to_messages'):
            messages = prompt_value.to_messages()
            # Get system message to extract candidates
            system_msg = str(messages[0].content) if messages else ""
        else:
            system_msg = str(prompt_value)

        llm.invocations.append(prompt_value)

        # Parse candidate IDs from the prompt
        ids = re.findall(r'ID (\d+):', system_msg)

        if ids:
            chosen_id = int(ids[0])  # Choose first by default
            result_dict = {
                "product_id": chosen_id,
                "reasoning": f"Mock LLM chose product {chosen_id}"
            }
        else:
            result_dict = {
                "product_id": 1,
                "reasoning": "Default mock choice"
            }

        # Return MockAIMessage with JSON content
        return MockAIMessage(json.dumps(result_dict))

    llm.invoke = mock_llm_invoke

    # Mock the | operator for chaining (prompt | llm | parser)
    def create_chain(*args):
        """Create a chain mock that runs through prompt -> llm -> parser"""
        chain = Mock()

        def chain_invoke(input_dict):
            # Simulate: prompt formats input -> llm processes -> parser parses
            # For our case, parser will extract JSON from AI message

            # Get the formatted prompt (first element in chain)
            # Then call LLM with it
            ai_message = mock_llm_invoke(input_dict)

            # Parse the JSON response
            return json.loads(ai_message.content)

        chain.invoke = chain_invoke
        return chain

    llm.__or__ = lambda self, other: create_chain(llm, other)

    return llm
