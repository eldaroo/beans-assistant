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
    register_product_with_stock,
    register_products_batch,
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


@pytest.mark.unit
@pytest.mark.database
class TestRegisterProductWithStock:
    """Tests for register_product_with_stock() atomic function."""

    def test_creates_product_and_stock_movement(self, test_db):
        result = register_product_with_stock({
            "sku": "BC-MANZ",
            "name": "Manzanas",
            "initial_stock": 15,
        })

        assert result["sku"] == "BC-MANZ"
        assert result["name"] == "Manzanas"
        assert result["initial_stock"] == 15
        assert result["current_stock"] == 15
        assert isinstance(result["product_id"], int)

        product = fetch_one("SELECT * FROM products WHERE sku = ?", ("BC-MANZ",))
        assert product is not None
        assert product["unit_price_cents"] is None
        assert product["unit_cost_cents"] == 0
        assert product["is_active"] == 1

        movement = fetch_one(
            "SELECT * FROM stock_movements WHERE product_id = ?",
            (result["product_id"],),
        )
        assert movement is not None
        assert movement["movement_type"] == "IN"
        assert movement["quantity"] == 15
        assert movement["reason"] == "Entrada inicial"

    def test_accepts_explicit_price_and_cost(self, test_db):
        result = register_product_with_stock({
            "sku": "BC-PEAR",
            "name": "Peras",
            "initial_stock": 10,
            "unit_price_cents": 200,
            "unit_cost_cents": 80,
        })

        product = fetch_one("SELECT * FROM products WHERE sku = ?", ("BC-PEAR",))
        assert product["unit_price_cents"] == 200
        assert product["unit_cost_cents"] == 80
        assert result["initial_stock"] == 10

    def test_rejects_zero_initial_stock(self, test_db):
        with pytest.raises(ValueError, match="initial_stock"):
            register_product_with_stock({
                "sku": "BC-ZERO",
                "name": "Zero",
                "initial_stock": 0,
            })

        # Producto no debe existir
        assert fetch_one("SELECT * FROM products WHERE sku = ?", ("BC-ZERO",)) is None

    def test_rejects_duplicate_sku(self, test_db):
        register_product_with_stock({
            "sku": "BC-DUP",
            "name": "Dup",
            "initial_stock": 5,
        })

        with pytest.raises(ValueError, match="ya existe"):
            register_product_with_stock({
                "sku": "BC-DUP",
                "name": "Dup2",
                "initial_stock": 7,
            })

    def test_rollback_on_stock_failure(self, test_db, monkeypatch):
        """Si el INSERT del stock_movement falla, el producto debe rollback."""
        import database

        original_get_conn = database.get_conn

        class FailingConn:
            """Wrapper que delega excepto en stock_movements INSERT."""

            def __init__(self, real_conn):
                self._real = real_conn

            def execute(self, query, *args, **kwargs):
                if "stock_movements" in query and "INSERT" in query:
                    raise RuntimeError("simulated stock insert failure")
                return self._real.execute(query, *args, **kwargs)

            def commit(self):
                self._real.commit()

            def rollback(self):
                self._real.rollback()

            def close(self):
                self._real.close()

            def __getattr__(self, name):
                return getattr(self._real, name)

        from contextlib import contextmanager

        @contextmanager
        def failing_get_conn():
            real_cm = original_get_conn()
            real_conn = real_cm.__enter__()
            wrapper = FailingConn(real_conn)
            try:
                yield wrapper
                real_cm.__exit__(None, None, None)
            except Exception:
                real_cm.__exit__(RuntimeError, RuntimeError("rollback"), None)
                raise

        monkeypatch.setattr("database.get_conn", failing_get_conn)

        with pytest.raises(RuntimeError, match="simulated stock insert failure"):
            register_product_with_stock({
                "sku": "BC-ROLLBACK",
                "name": "Rollback",
                "initial_stock": 5,
            })

        # Restore unpatched conn for verification
        monkeypatch.setattr("database.get_conn", original_get_conn)

        # Producto NO debe existir tras rollback
        assert fetch_one("SELECT * FROM products WHERE sku = ?", ("BC-ROLLBACK",)) is None


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


# ==============================================================================
# REGISTER_PRODUCTS_BATCH (atomic multi-product creation, PR-4)
# ==============================================================================

@pytest.mark.unit
@pytest.mark.database
class TestRegisterProductsBatch:
    """All-or-nothing batch creation. Per Atlas review of PR-4, the contract
    is atomic: any failure rolls back the entire batch."""

    def test_creates_three_products_in_one_call(self, test_db):
        result = register_products_batch([
            {"sku": "BATCH-1", "name": "Peras verdes", "unit_price_cents": 500, "unit_cost_cents": 0},
            {"sku": "BATCH-2", "name": "Manzanas rojas", "unit_price_cents": 300, "unit_cost_cents": 0},
            {"sku": "BATCH-3", "name": "Bananas", "unit_price_cents": 200, "unit_cost_cents": 0},
        ])

        assert len(result) == 3
        assert result[0]["sku"] == "BATCH-1"
        assert result[1]["sku"] == "BATCH-2"
        assert result[2]["sku"] == "BATCH-3"
        rows = fetch_all("SELECT sku FROM products WHERE sku LIKE 'BATCH-%' ORDER BY sku")
        assert [r["sku"] for r in rows] == ["BATCH-1", "BATCH-2", "BATCH-3"]

    def test_duplicate_sku_rolls_back_entire_batch(self, test_db):
        # Pre-existing product whose SKU collides with item 2 of the batch.
        register_product({
            "sku": "EXISTS-1",
            "name": "Pre-existing",
            "unit_price_cents": 100,
            "unit_cost_cents": 0,
        })

        with pytest.raises(ValueError) as exc:
            register_products_batch([
                {"sku": "BATCH-A", "name": "First", "unit_price_cents": 500, "unit_cost_cents": 0},
                {"sku": "EXISTS-1", "name": "Second (collides)", "unit_price_cents": 500, "unit_cost_cents": 0},
                {"sku": "BATCH-C", "name": "Third", "unit_price_cents": 500, "unit_cost_cents": 0},
            ])

        # Error must name the offending row so the user can fix it.
        assert "EXISTS-1" in str(exc.value) or "Second" in str(exc.value)

        # Atomicity: neither BATCH-A nor BATCH-C must have landed.
        rows = fetch_all("SELECT sku FROM products WHERE sku IN ('BATCH-A', 'BATCH-C')")
        assert len(rows) == 0

    def test_accepts_null_unit_price_cents(self, test_db):
        """Multi-product create should support price-pending items so the
        user can populate stock first and price later."""
        register_products_batch([
            {"sku": "NPRC-1", "name": "Sin precio", "unit_price_cents": None, "unit_cost_cents": 0},
        ])
        row = fetch_one("SELECT name, unit_price_cents FROM products WHERE sku = ?", ("NPRC-1",))
        assert row["name"] == "Sin precio"
        assert row["unit_price_cents"] is None

    def test_empty_list_raises(self, test_db):
        with pytest.raises(ValueError):
            register_products_batch([])
