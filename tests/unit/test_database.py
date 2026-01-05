"""
Unit tests for database.py business operations.

Tests cover:
- Product registration (5 tests)
- Stock management (8 tests)
- Sales operations (10 tests)
- Expense management (4 tests)
- Cancellation operations (3 tests)

Total: 30 tests
"""
import pytest
from database import (
    register_product,
    add_stock,
    register_sale,
    register_expense,
    cancel_sale,
    cancel_expense,
    fetch_one,
    fetch_all,
    get_last_sale,
    get_last_expense,
)


# ==============================================================================
# PRODUCT REGISTRATION TESTS (5 tests)
# ==============================================================================

@pytest.mark.unit
@pytest.mark.database
class TestProductRegistration:
    """Tests for register_product() function."""

    def test_register_product_success(self, test_db):
        """Test successful product registration."""
        result = register_product({
            "sku": "TEST-001",
            "name": "Test Product",
            "description": "A test product",
            "unit_price_cents": 1000,
            "unit_cost_cents": 500
        })

        assert result["status"] == "ok"
        assert result["sku"] == "TEST-001"

        # Verify in database
        row = fetch_one("SELECT * FROM products WHERE sku = ?", ("TEST-001",))
        assert row is not None
        assert row["name"] == "Test Product"
        assert row["unit_price_cents"] == 1000
        assert row["unit_cost_cents"] == 500
        assert row["is_active"] == 1

    def test_register_product_duplicate_sku_raises_error(self, test_db):
        """Test that duplicate SKU raises an error."""
        register_product({
            "sku": "DUP-001",
            "name": "First Product",
            "unit_price_cents": 1000,
            "unit_cost_cents": 500
        })

        # Attempting to register with duplicate SKU should fail
        with pytest.raises(Exception):  # SQLite UNIQUE constraint violation
            register_product({
                "sku": "DUP-001",
                "name": "Duplicate SKU Product",
                "unit_price_cents": 2000,
                "unit_cost_cents": 1000
            })

    def test_register_product_with_description(self, test_db):
        """Test product registration with optional description."""
        result = register_product({
            "sku": "DESC-001",
            "name": "Product with Description",
            "description": "This product has a detailed description",
            "unit_price_cents": 1500,
            "unit_cost_cents": 800
        })

        assert result["status"] == "ok"

        row = fetch_one("SELECT * FROM products WHERE sku = ?", ("DESC-001",))
        assert row["description"] == "This product has a detailed description"

    def test_register_product_without_description(self, test_db):
        """Test product registration without description (NULL)."""
        result = register_product({
            "sku": "NO-DESC-001",
            "name": "Product without Description",
            "description": None,
            "unit_price_cents": 1200,
            "unit_cost_cents": 600
        })

        assert result["status"] == "ok"

        row = fetch_one("SELECT * FROM products WHERE sku = ?", ("NO-DESC-001",))
        assert row["description"] is None

    def test_register_product_with_zero_cost(self, test_db):
        """Test product registration with zero cost (valid edge case)."""
        result = register_product({
            "sku": "ZERO-COST-001",
            "name": "Product with Zero Cost",
            "unit_price_cents": 2000,
            "unit_cost_cents": 0
        })

        assert result["status"] == "ok"

        row = fetch_one("SELECT * FROM products WHERE sku = ?", ("ZERO-COST-001",))
        assert row["unit_cost_cents"] == 0


# ==============================================================================
# STOCK MANAGEMENT TESTS (8 tests)
# ==============================================================================

@pytest.mark.unit
@pytest.mark.database
class TestStockManagement:
    """Tests for add_stock() function."""

    def test_add_stock_increases_quantity(self, populated_db):
        """Test that adding stock increases the quantity."""
        result = add_stock({
            "product_id": 1,
            "quantity": 50,
            "reason": "Initial stock"
        })

        assert result["status"] == "ok"
        assert result["message"] == "Stock updated"
        assert result["product_id"] == 1
        assert result["current_stock"] == 50

    def test_add_stock_with_custom_reason(self, populated_db):
        """Test stock addition with custom reason."""
        add_stock({
            "product_id": 2,
            "quantity": 25,
            "reason": "Restock after sale"
        })

        # Verify stock movement was recorded
        movement = fetch_one(
            "SELECT * FROM stock_movements WHERE product_id = ? ORDER BY created_at DESC LIMIT 1",
            (2,)
        )
        assert movement["reason"] == "Restock after sale"
        assert movement["quantity"] == 25

    def test_add_stock_movement_type_in(self, populated_db):
        """Test stock movement with type IN."""
        result = add_stock({
            "product_id": 1,
            "quantity": 20,
            "movement_type": "IN"
        })

        assert result["current_stock"] == 20

        movement = fetch_one(
            "SELECT * FROM stock_movements WHERE product_id = ? LIMIT 1",
            (1,)
        )
        assert movement["movement_type"] == "IN"

    def test_add_stock_movement_type_adjustment(self, populated_db):
        """Test stock movement with type ADJUSTMENT."""
        result = add_stock({
            "product_id": 1,
            "quantity": 15,
            "movement_type": "ADJUSTMENT"
        })

        assert result["current_stock"] == 15

        movement = fetch_one(
            "SELECT * FROM stock_movements WHERE product_id = ? LIMIT 1",
            (1,)
        )
        assert movement["movement_type"] == "ADJUSTMENT"

    def test_add_stock_returns_current_stock(self, populated_db):
        """Test that add_stock returns the correct current stock."""
        # Add stock twice
        add_stock({"product_id": 3, "quantity": 10})
        result = add_stock({"product_id": 3, "quantity": 5})

        # Should return sum of both additions
        assert result["current_stock"] == 15

    def test_add_stock_multiple_movements(self, populated_db):
        """Test multiple stock movements accumulate correctly."""
        add_stock({"product_id": 1, "quantity": 10})
        add_stock({"product_id": 1, "quantity": 20})
        result = add_stock({"product_id": 1, "quantity": 15})

        assert result["current_stock"] == 45

    def test_stock_current_view_accuracy(self, populated_db):
        """Test that stock_current view calculates correctly."""
        # Add IN movements
        add_stock({"product_id": 1, "quantity": 100, "movement_type": "IN"})
        add_stock({"product_id": 1, "quantity": 50, "movement_type": "IN"})

        # Check view
        stock = fetch_one("SELECT * FROM stock_current WHERE product_id = ?", (1,))
        assert stock["stock_qty"] == 150

    @pytest.mark.parametrize("movement_type,quantity,expected", [
        ("IN", 20, 20),
        ("ADJUSTMENT", 15, 15),
    ])
    def test_add_stock_parametrized_movement_types(self, populated_db, movement_type, quantity, expected):
        """Parametrized test for different movement types."""
        result = add_stock({
            "product_id": 4,
            "quantity": quantity,
            "movement_type": movement_type
        })

        assert result["current_stock"] == expected


# ==============================================================================
# SALES OPERATIONS TESTS (10 tests)
# ==============================================================================

@pytest.mark.unit
@pytest.mark.database
class TestSalesOperations:
    """Tests for register_sale() function."""

    def test_register_sale_paid_decreases_stock(self, populated_db):
        """Test that PAID sale decreases stock."""
        # Add initial stock
        add_stock({"product_id": 1, "quantity": 100})

        # Register PAID sale
        result = register_sale({
            "status": "PAID",
            "items": [{"product_id": 1, "quantity": 10}]
        })

        assert result["status"] == "ok"
        assert "sale_id" in result

        # Verify stock decreased
        stock = fetch_one("SELECT * FROM stock_current WHERE product_id = ?", (1,))
        assert stock["stock_qty"] == 90

    def test_register_sale_pending_no_stock_change(self, populated_db):
        """Test that PENDING sale does NOT decrease stock."""
        # Add initial stock
        add_stock({"product_id": 1, "quantity": 100})

        # Register PENDING sale
        register_sale({
            "status": "PENDING",
            "items": [{"product_id": 1, "quantity": 10}]
        })

        # Verify stock unchanged
        stock = fetch_one("SELECT * FROM stock_current WHERE product_id = ?", (1,))
        assert stock["stock_qty"] == 100

    def test_register_sale_insufficient_stock_raises_error(self, populated_db):
        """Test that sale with insufficient stock raises error."""
        # Add only 5 units of stock
        add_stock({"product_id": 1, "quantity": 5})

        # Try to sell 10 units (should fail)
        with pytest.raises(Exception, match="No hay suficiente stock"):
            register_sale({
                "status": "PAID",
                "items": [{"product_id": 1, "quantity": 10}]
            })

    def test_register_sale_multiple_items(self, populated_db):
        """Test sale with multiple items."""
        # Add stock for products
        add_stock({"product_id": 1, "quantity": 50})
        add_stock({"product_id": 2, "quantity": 30})

        result = register_sale({
            "status": "PAID",
            "items": [
                {"product_id": 1, "quantity": 5},
                {"product_id": 2, "quantity": 3}
            ]
        })

        assert result["status"] == "ok"

        # Verify both stocks decreased
        stock1 = fetch_one("SELECT * FROM stock_current WHERE product_id = ?", (1,))
        stock2 = fetch_one("SELECT * FROM stock_current WHERE product_id = ?", (2,))
        assert stock1["stock_qty"] == 45
        assert stock2["stock_qty"] == 27

    def test_register_sale_custom_price_override(self, populated_db):
        """Test sale with custom price (overrides catalog price)."""
        add_stock({"product_id": 1, "quantity": 50})

        result = register_sale({
            "status": "PAID",
            "items": [
                {"product_id": 1, "quantity": 2, "unit_price_cents": 5000}  # Custom price $50
            ]
        })

        assert result["status"] == "ok"

        # Verify total reflects custom price (2 * $50 = $100)
        assert result["total_usd"] == 100.0

    def test_register_sale_by_sku_reference(self, populated_db):
        """Test sale using SKU as product reference."""
        add_stock({"product_id": 1, "quantity": 50})

        result = register_sale({
            "status": "PAID",
            "items": [
                {"product_ref": "BC-BRACELET-CLASSIC", "quantity": 5}
            ]
        })

        assert result["status"] == "ok"
        assert result["total_usd"] == 175.0  # 5 * $35

    def test_register_sale_by_name_reference(self, populated_db):
        """Test sale using product name as reference."""
        add_stock({"product_id": 2, "quantity": 50})

        result = register_sale({
            "status": "PAID",
            "items": [
                {"product_ref": "Pulsera de Granos de Café - Negra", "quantity": 3}
            ]
        })

        assert result["status"] == "ok"
        assert result["total_usd"] == 105.0  # 3 * $35

    def test_register_sale_updates_revenue_view(self, populated_db):
        """Test that sale updates revenue_paid view."""
        add_stock({"product_id": 1, "quantity": 100})

        register_sale({
            "status": "PAID",
            "items": [{"product_id": 1, "quantity": 10}]
        })

        # Check revenue view
        revenue = fetch_one("SELECT * FROM revenue_paid")
        assert revenue["total_revenue_cents"] == 35000  # 10 * $35

    def test_register_sale_updates_profit_view(self, populated_db):
        """Test that sale updates profit_summary view."""
        add_stock({"product_id": 1, "quantity": 100})

        result = register_sale({
            "status": "PAID",
            "items": [{"product_id": 1, "quantity": 10}]
        })

        # Note: profit_summary view calculates revenue - expenses (doesn't track COGS)
        # Profit = revenue - expenses = $350 - $0 = $350
        assert result["profit_usd"] == 350.0

    def test_register_sale_generates_unique_sale_number(self, populated_db):
        """Test that each sale gets a unique sale_number."""
        add_stock({"product_id": 1, "quantity": 100})

        result1 = register_sale({
            "status": "PAID",
            "items": [{"product_id": 1, "quantity": 1}]
        })

        result2 = register_sale({
            "status": "PAID",
            "items": [{"product_id": 1, "quantity": 1}]
        })

        sale1 = fetch_one("SELECT * FROM sales WHERE id = ?", (result1["sale_id"],))
        sale2 = fetch_one("SELECT * FROM sales WHERE id = ?", (result2["sale_id"],))

        assert sale1["sale_number"] != sale2["sale_number"]


# ==============================================================================
# EXPENSE MANAGEMENT TESTS (4 tests)
# ==============================================================================

@pytest.mark.unit
@pytest.mark.database
class TestExpenseManagement:
    """Tests for register_expense() function."""

    def test_register_expense_with_all_fields(self, test_db):
        """Test expense registration with all fields."""
        result = register_expense({
            "amount_cents": 5000,
            "description": "Office supplies",
            "category": "SUPPLIES",
            "expense_date": "2024-01-15"
        })

        assert result["status"] == "ok"
        assert "expense_id" in result
        assert result["amount_usd"] == 50.0
        assert result["category"] == "SUPPLIES"

        # Verify in database
        expense = fetch_one("SELECT * FROM expenses WHERE id = ?", (result["expense_id"],))
        assert expense["description"] == "Office supplies"
        assert expense["expense_date"] == "2024-01-15"

    def test_register_expense_with_defaults(self, test_db):
        """Test expense registration with minimal fields (uses defaults)."""
        result = register_expense({
            "amount_cents": 3000,
            "description": "Misc expense"
        })

        assert result["status"] == "ok"
        assert result["amount_usd"] == 30.0
        assert result["category"] == "GENERAL"  # Default category

    def test_register_expense_updates_profit(self, populated_db):
        """Test that expense updates profit calculation."""
        # First make a sale to have revenue
        add_stock({"product_id": 1, "quantity": 100})
        register_sale({
            "status": "PAID",
            "items": [{"product_id": 1, "quantity": 10}]
        })
        # Profit after sale = $350 (revenue - expenses, no COGS tracking)

        # Register expense
        result = register_expense({
            "amount_cents": 5000,  # $50 expense
            "description": "Shipping costs"
        })

        # Profit should decrease: $350 - $50 = $300
        assert result["profit_usd"] == 300.0

    def test_register_expense_with_category(self, test_db):
        """Test expense registration with different categories."""
        categories = ["SUPPLIES", "MARKETING", "SHIPPING", "GENERAL"]

        for category in categories:
            result = register_expense({
                "amount_cents": 1000,
                "description": f"Test {category} expense",
                "category": category
            })

            assert result["category"] == category


# ==============================================================================
# CANCELLATION OPERATIONS TESTS (3 tests)
# ==============================================================================

@pytest.mark.unit
@pytest.mark.database
class TestCancellationOperations:
    """Tests for cancel_sale() and cancel_expense() functions."""

    def test_cancel_sale_restores_stock(self, populated_db):
        """Test that canceling a PAID sale restores stock."""
        # Add stock and make sale
        add_stock({"product_id": 1, "quantity": 100})
        result = register_sale({
            "status": "PAID",
            "items": [{"product_id": 1, "quantity": 10}]
        })
        sale_id = result["sale_id"]

        # Stock should be 90 after sale
        stock_before = fetch_one("SELECT * FROM stock_current WHERE product_id = ?", (1,))
        assert stock_before["stock_qty"] == 90

        # Cancel the sale
        cancel_result = cancel_sale(sale_id)

        assert cancel_result["status"] == "ok"
        assert cancel_result["cancelled_amount"] == 350.0

        # Stock should be restored to 100
        stock_after = fetch_one("SELECT * FROM stock_current WHERE product_id = ?", (1,))
        assert stock_after["stock_qty"] == 100

    def test_cancel_sale_updates_revenue(self, populated_db):
        """Test that canceling sale updates revenue."""
        # Make two sales
        add_stock({"product_id": 1, "quantity": 100})
        result1 = register_sale({
            "status": "PAID",
            "items": [{"product_id": 1, "quantity": 10}]
        })
        result2 = register_sale({
            "status": "PAID",
            "items": [{"product_id": 1, "quantity": 5}]
        })

        # Revenue should be $525 (10*$35 + 5*$35)
        revenue_before = fetch_one("SELECT * FROM revenue_paid")
        assert revenue_before["total_revenue_cents"] == 52500

        # Cancel first sale
        cancel_result = cancel_sale(result1["sale_id"])

        # Revenue should now be $175 (only 5*$35 remaining)
        assert cancel_result["revenue_usd"] == 175.0

    def test_cancel_expense_updates_profit(self, populated_db):
        """Test that canceling expense updates profit."""
        # Make a sale and record an expense
        add_stock({"product_id": 1, "quantity": 100})
        register_sale({
            "status": "PAID",
            "items": [{"product_id": 1, "quantity": 10}]
        })
        # Profit = $350 (revenue - expenses, no COGS tracking)

        expense_result = register_expense({
            "amount_cents": 5000,  # $50
            "description": "Test expense"
        })
        # Profit = $300

        # Cancel the expense
        cancel_result = cancel_expense(expense_result["expense_id"])

        assert cancel_result["status"] == "ok"
        assert cancel_result["cancelled_amount"] == 50.0

        # Profit should be restored to $350
        assert cancel_result["profit_usd"] == 350.0
