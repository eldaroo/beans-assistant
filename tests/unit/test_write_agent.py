"""
Unit tests for agents/write_agent.py operation execution.

Tests cover:
- REGISTER_SALE handler (5 tests)
- REGISTER_EXPENSE handler (3 tests)
- REGISTER_PRODUCT handler (3 tests)
- ADD_STOCK handler (4 tests)
- CANCEL_SALE handler (3 tests)
- CANCEL_EXPENSE handler (2 tests)

Total: 20 tests
"""
import pytest
from agents.write_agent import create_write_agent
from agents.state import AgentState
from database import add_stock, register_sale, register_expense


# ==============================================================================
# REGISTER_SALE HANDLER TESTS (5 tests)
# ==============================================================================

@pytest.mark.unit
class TestRegisterSaleHandler:
    """Tests for REGISTER_SALE operation handler in write agent."""

    def test_execute_register_sale_success(self, populated_db):
        """Test successful sale registration execution."""
        # Add stock first
        add_stock({"product_id": 1, "quantity": 100})

        # Create write agent and execute
        write_agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_SALE",
            "normalized_entities": {
                "items": [
                    {"product_id": 1, "quantity": 5, "resolved_name": "Pulsera Clásica"}
                ],
                "status": "PAID"
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert result["operation_result"] is not None
        assert result["operation_result"]["status"] == "ok"
        assert "final_answer" in result
        assert "Venta registrada" in result["final_answer"]

    def test_execute_register_sale_missing_items_returns_error(self, populated_db):
        """Test that sale without items returns friendly error."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_SALE",
            "normalized_entities": {},  # No items
            "missing_fields": ["items"],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert "error" in result
        assert "final_answer" in result
        assert "productos" in result["final_answer"].lower()

    def test_execute_register_sale_formats_friendly_response(self, populated_db):
        """Test that sale response is user-friendly in Spanish."""
        add_stock({"product_id": 1, "quantity": 100})

        write_agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_SALE",
            "normalized_entities": {
                "items": [
                    {"product_id": 1, "quantity": 3, "resolved_name": "Pulsera Clásica"}
                ],
                "status": "PAID"
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        final_answer = result["final_answer"]
        assert "✅" in final_answer or "Venta registrada" in final_answer
        assert "Pulsera Clásica" in final_answer
        assert "$" in final_answer  # Should include total amount

    def test_execute_register_sale_includes_revenue_profit(self, populated_db):
        """Test that sale response includes revenue and profit."""
        add_stock({"product_id": 1, "quantity": 100})

        write_agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_SALE",
            "normalized_entities": {
                "items": [
                    {"product_id": 1, "quantity": 10, "resolved_name": "Pulsera Clásica"}
                ],
                "status": "PAID"
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert result["operation_result"]["total_usd"] == 350.0
        assert "revenue_usd" in result["operation_result"]
        assert "profit_usd" in result["operation_result"]

    def test_execute_register_sale_handles_multiple_items(self, populated_db):
        """Test sale with multiple items."""
        add_stock({"product_id": 1, "quantity": 100})
        add_stock({"product_id": 2, "quantity": 100})

        write_agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_SALE",
            "normalized_entities": {
                "items": [
                    {"product_id": 1, "quantity": 5, "resolved_name": "Pulsera Clásica"},
                    {"product_id": 2, "quantity": 3, "resolved_name": "Pulsera Negra"}
                ],
                "status": "PAID"
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        final_answer = result["final_answer"]
        assert "Pulsera Clásica" in final_answer
        assert "Pulsera Negra" in final_answer
        assert "5" in final_answer
        assert "3" in final_answer


# ==============================================================================
# REGISTER_EXPENSE HANDLER TESTS (3 tests)
# ==============================================================================

@pytest.mark.unit
class TestRegisterExpenseHandler:
    """Tests for REGISTER_EXPENSE operation handler in write agent."""

    def test_execute_register_expense_success(self, populated_db):
        """Test successful expense registration execution."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_EXPENSE",
            "normalized_entities": {
                "amount_cents": 5000,  # $50
                "description": "Shipping costs",
                "category": "SHIPPING"
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert result["operation_result"] is not None
        assert result["operation_result"]["status"] == "ok"
        assert result["operation_result"]["amount_usd"] == 50.0
        assert "Gasto registrado" in result["final_answer"]

    def test_execute_register_expense_missing_amount_returns_error(self, test_db):
        """Test that expense without amount returns friendly error."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_EXPENSE",
            "normalized_entities": {
                "description": "Some expense"
                # Missing amount_cents
            },
            "missing_fields": ["amount"],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert "error" in result
        assert "monto" in result["final_answer"].lower()

    def test_execute_register_expense_formats_friendly_response(self, test_db):
        """Test that expense response is user-friendly in Spanish."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_EXPENSE",
            "normalized_entities": {
                "amount_cents": 3000,  # $30
                "description": "Marketing materials"
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        final_answer = result["final_answer"]
        assert "💸" in final_answer or "Gasto registrado" in final_answer
        assert "Marketing materials" in final_answer
        assert "$30" in final_answer or "$30.00" in final_answer


# ==============================================================================
# REGISTER_PRODUCT HANDLER TESTS (3 tests)
# ==============================================================================

@pytest.mark.unit
class TestRegisterProductHandler:
    """Tests for REGISTER_PRODUCT operation handler in write agent."""

    def test_execute_register_product_success(self, test_db):
        """Test successful product registration execution."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_PRODUCT",
            "normalized_entities": {
                "sku": "NEW-PRODUCT-001",
                "name": "New Product",
                "unit_price_cents": 2000,
                "unit_cost_cents": 1000
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert result["operation_result"] is not None
        assert result["operation_result"]["status"] == "ok"
        assert "Producto creado" in result["final_answer"]

    def test_execute_register_product_missing_fields_returns_error(self, test_db):
        """Test that product without required fields returns friendly error."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_PRODUCT",
            "normalized_entities": {
                "sku": "INCOMPLETE-001"
                # Missing name and unit_price_cents
            },
            "missing_fields": ["name", "unit_price_cents"],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert "error" in result
        assert "nombre" in result["final_answer"].lower() or "precio" in result["final_answer"].lower()

    def test_execute_register_product_formats_friendly_response(self, test_db):
        """Test that product response is user-friendly in Spanish."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "REGISTER_PRODUCT",
            "normalized_entities": {
                "sku": "PRETTY-PRODUCT",
                "name": "Beautiful Product",
                "unit_price_cents": 4500,
                "unit_cost_cents": 2000
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        final_answer = result["final_answer"]
        assert "✨" in final_answer or "Producto creado" in final_answer
        assert "Beautiful Product" in final_answer
        assert "PRETTY-PRODUCT" in final_answer
        assert "$45" in final_answer or "$45.00" in final_answer


# ==============================================================================
# ADD_STOCK HANDLER TESTS (4 tests)
# ==============================================================================

@pytest.mark.unit
class TestAddStockHandler:
    """Tests for ADD_STOCK operation handler in write agent."""

    def test_execute_add_stock_single_product(self, populated_db):
        """Test stock addition for single product."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "ADD_STOCK",
            "normalized_entities": {
                "product_id": 1,
                "quantity": 50,
                "resolved_name": "Pulsera Clásica"
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert result["operation_result"] is not None
        assert "Stock actualizado" in result["final_answer"]
        assert "+50" in result["final_answer"]
        assert "Pulsera Clásica" in result["final_answer"]

    def test_execute_add_stock_multiple_items(self, populated_db):
        """Test stock addition for multiple products."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "ADD_STOCK",
            "normalized_entities": {
                "items": [
                    {"product_id": 1, "quantity": 400, "resolved_name": "Pulsera Clásica"},
                    {"product_id": 3, "quantity": 200, "resolved_name": "Pulsera Dorada"}
                ]
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        final_answer = result["final_answer"]
        assert "Stock actualizado" in final_answer
        assert "+400" in final_answer
        assert "+200" in final_answer
        assert "Pulsera Clásica" in final_answer
        assert "Pulsera Dorada" in final_answer

    def test_execute_add_stock_formats_friendly_response(self, populated_db):
        """Test that stock update response is user-friendly in Spanish."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "ADD_STOCK",
            "normalized_entities": {
                "product_id": 2,
                "quantity": 75,
                "resolved_name": "Pulsera Negra"
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        final_answer = result["final_answer"]
        assert "📦" in final_answer or "Stock actualizado" in final_answer
        assert "Pulsera Negra" in final_answer
        assert "75" in final_answer
        assert "stock actual" in final_answer.lower()

    def test_execute_add_stock_missing_quantity_returns_error(self, populated_db):
        """Test that stock update without quantity returns friendly error."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "ADD_STOCK",
            "normalized_entities": {
                "product_id": 1
                # Missing quantity
            },
            "missing_fields": ["quantity"],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert "error" in result
        assert "cantidad" in result["final_answer"].lower()


@pytest.mark.unit
@pytest.mark.database
class TestRegisterSalePriceGuard:
    """REGISTER_SALE must block when any product has NULL unit_price_cents."""

    def _state(self, items):
        return {
            "operation_type": "REGISTER_SALE",
            "normalized_entities": {"items": items, "status": "PAID"},
            "missing_fields": [],
            "intent": "WRITE_OPERATION",
        }

    def test_blocks_sale_when_product_has_null_price(self, populated_db):
        """A product created via REGISTER_PRODUCT_WITH_STOCK has NULL price.
        Selling it without an inline price must be blocked."""
        from database import register_product_with_stock, add_stock

        result_create = register_product_with_stock({
            "sku": "BC-NULLPRICE",
            "name": "Manzanas",
            "initial_stock": 50,
        })
        product_id = result_create["product_id"]

        write_agent = create_write_agent()
        result = write_agent(self._state([
            {"product_id": product_id, "quantity": 3, "resolved_name": "Manzanas"}
        ]))

        assert result["operation_result"] is None
        assert "error" in result
        msg = result["final_answer"]
        assert "Manzanas" in msg
        assert "precio" in msg.lower()
        # No registró venta ni line item
        from database import fetch_one
        row = fetch_one(
            "SELECT COUNT(*) AS n FROM sale_items WHERE product_id = ?",
            (product_id,),
        )
        assert row["n"] == 0

    def test_inline_price_override_allows_sale(self, populated_db):
        """If the user gives an explicit per-item price, the sale proceeds
        even when the catalog price is NULL."""
        from database import register_product_with_stock

        result_create = register_product_with_stock({
            "sku": "BC-NULLPRICE-OK",
            "name": "Peras",
            "initial_stock": 20,
        })
        product_id = result_create["product_id"]

        write_agent = create_write_agent()
        result = write_agent(self._state([
            {
                "product_id": product_id,
                "quantity": 2,
                "resolved_name": "Peras",
                "unit_price_cents": 250,
            }
        ]))

        assert result["operation_result"] is not None
        assert result["operation_result"]["status"] == "ok"

    def test_existing_priced_product_sale_unchanged(self, populated_db):
        """Regression: products with a normal price still sell as before."""
        from database import add_stock
        add_stock({"product_id": 1, "quantity": 100})

        write_agent = create_write_agent()
        result = write_agent(self._state([
            {"product_id": 1, "quantity": 5, "resolved_name": "Pulsera Clásica"}
        ]))

        assert result["operation_result"] is not None
        assert result["operation_result"]["status"] == "ok"


@pytest.mark.unit
@pytest.mark.database
class TestRegisterProductWithStockHandler:
    """Tests for REGISTER_PRODUCT_WITH_STOCK operation handler."""

    def _state(self, entities):
        return {
            "operation_type": "REGISTER_PRODUCT_WITH_STOCK",
            "normalized_entities": entities,
            "missing_fields": [],
            "intent": "WRITE_OPERATION",
        }

    def test_creates_product_and_registers_stock(self, populated_db):
        from database import fetch_one

        write_agent = create_write_agent()
        result = write_agent(self._state({
            "name": "Manzanas",
            "initial_stock": 15,
        }))

        assert result["operation_result"] is not None
        assert result["operation_result"]["initial_stock"] == 15
        assert result["operation_result"]["current_stock"] == 15

        # Producto creado en DB con precio NULL
        product = fetch_one(
            "SELECT * FROM products WHERE name = ?",
            ("Manzanas",),
        )
        assert product is not None
        assert product["unit_price_cents"] is None

    def test_summary_asks_for_price(self, populated_db):
        write_agent = create_write_agent()
        result = write_agent(self._state({
            "name": "Peras",
            "initial_stock": 10,
        }))

        msg = result["final_answer"]
        assert "Peras" in msg
        assert "10" in msg
        assert "precio" in msg.lower()
        # Promete primera venta como hook tardío
        assert "primera venta" in msg.lower()

    def test_missing_name_returns_error(self, populated_db):
        write_agent = create_write_agent()
        result = write_agent(self._state({
            "initial_stock": 5,
        }))

        assert result["operation_result"] is None
        assert "error" in result
        assert "fall" in result["error"].lower() or "falt" in result["error"].lower()

    def test_missing_stock_returns_error(self, populated_db):
        write_agent = create_write_agent()
        result = write_agent(self._state({
            "name": "Bananas",
        }))

        assert result["operation_result"] is None
        assert "error" in result

    def test_uses_provided_sku(self, populated_db):
        from database import fetch_one

        write_agent = create_write_agent()
        result = write_agent(self._state({
            "name": "Sandias",
            "initial_stock": 8,
            "sku": "BC-CUSTOM-SKU",
        }))

        assert result["operation_result"]["sku"] == "BC-CUSTOM-SKU"
        product = fetch_one(
            "SELECT * FROM products WHERE sku = ?",
            ("BC-CUSTOM-SKU",),
        )
        assert product is not None


# ==============================================================================
# CANCEL_SALE HANDLER TESTS (3 tests)
# ==============================================================================

@pytest.mark.unit
class TestCancelSaleHandler:
    """Tests for CANCEL_SALE operation handler in write agent."""

    def test_execute_cancel_sale_last_sale(self, populated_db):
        """Test canceling the last sale."""
        # Create a sale first
        add_stock({"product_id": 1, "quantity": 100})
        register_sale({
            "status": "PAID",
            "items": [{"product_id": 1, "quantity": 10}]
        })

        write_agent = create_write_agent()
        state = {
            "operation_type": "CANCEL_SALE",
            "normalized_entities": {
                "target": "last"
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert result["operation_result"] is not None
        assert "Venta cancelada" in result["final_answer"]

    def test_execute_cancel_sale_specific_id(self, populated_db):
        """Test canceling a sale by specific ID."""
        # Create a sale first
        add_stock({"product_id": 1, "quantity": 100})
        sale_result = register_sale({
            "status": "PAID",
            "items": [{"product_id": 1, "quantity": 5}]
        })
        sale_id = sale_result["sale_id"]

        write_agent = create_write_agent()
        state = {
            "operation_type": "CANCEL_SALE",
            "normalized_entities": {
                "target": str(sale_id)
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert result["operation_result"] is not None
        assert result["operation_result"]["status"] == "ok"

    def test_execute_cancel_sale_no_sales_returns_error(self, populated_db):
        """Test that canceling when no sales exist returns friendly error."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "CANCEL_SALE",
            "normalized_entities": {
                "target": "last"
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert "error" in result
        assert "Operación fallida" in result["final_answer"]


# ==============================================================================
# CANCEL_EXPENSE HANDLER TESTS (2 tests)
# ==============================================================================

@pytest.mark.unit
class TestCancelExpenseHandler:
    """Tests for CANCEL_EXPENSE operation handler in write agent."""

    def test_execute_cancel_expense_last_expense(self, populated_db):
        """Test canceling the last expense."""
        # Create an expense first
        register_expense({
            "amount_cents": 2000,
            "description": "Test expense"
        })

        write_agent = create_write_agent()
        state = {
            "operation_type": "CANCEL_EXPENSE",
            "normalized_entities": {
                "target": "last"
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert result["operation_result"] is not None
        assert "Gasto cancelado" in result["final_answer"]

    def test_execute_cancel_expense_no_expenses_returns_error(self, populated_db):
        """Test that canceling when no expenses exist returns friendly error."""
        write_agent = create_write_agent()
        state = {
            "operation_type": "CANCEL_EXPENSE",
            "normalized_entities": {
                "target": "last"
            },
            "missing_fields": [],
            "intent": "WRITE_OPERATION"
        }

        result = write_agent(state)

        assert "error" in result
        assert "Operación fallida" in result["final_answer"]
