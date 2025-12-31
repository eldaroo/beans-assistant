"""
Test the complete flow from user message to resolved product.
"""
from graph import create_business_agent_graph


def test_sale_resolution():
    """Test that 'acabo de vender 20 doradas' correctly resolves to gold bracelets."""

    # Create agent graph
    graph = create_business_agent_graph()

    # Test message
    user_message = "acabo de vender 20 doradas"

    print(f"Testing message: '{user_message}'")
    print("-" * 80)

    # Initial state
    state = {
        "messages": [],
        "user_input": user_message,
        "normalized_entities": {}
    }

    try:
        # Run graph
        result = graph.invoke(state)

        # Check results
        print("\nResults:")
        print(f"  Intent: {result.get('intent')}")
        print(f"  Operation Type: {result.get('operation_type')}")
        print(f"  Normalized Entities: {result.get('normalized_entities')}")

        # Check if product was correctly resolved
        entities = result.get('normalized_entities', {})
        items = entities.get('items', [])

        if items:
            for i, item in enumerate(items):
                product_id = item.get('product_id')
                product_name = item.get('resolved_name', 'Unknown')
                quantity = item.get('quantity')

                print(f"\n  Item {i + 1}:")
                print(f"    Product ID: {product_id}")
                print(f"    Product Name: {product_name}")
                print(f"    Quantity: {quantity}")

                # Verify it's the gold bracelet (product_id=3)
                if product_id == 3 and 'Dorada' in product_name:
                    print(f"\n[PASS] Correctly resolved to Gold bracelet (ID: 3)")
                    return True
                else:
                    print(f"\n[FAIL] Resolved to wrong product! Expected ID: 3 (Dorada), Got ID: {product_id}")
                    return False
        else:
            print("\n[FAIL] No items found in resolved entities")
            return False

    except Exception as e:
        print(f"\n[ERROR] Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_sale_resolution()
    exit(0 if success else 1)
