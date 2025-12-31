"""
Test various user message patterns to ensure robust product resolution.
"""
from graph import create_business_agent_graph


def test_message(message, expected_product_id, expected_product_keyword):
    """Test a single message."""
    graph = create_business_agent_graph()

    state = {
        "messages": [],
        "user_input": message,
        "normalized_entities": {}
    }

    try:
        result = graph.invoke(state)
        entities = result.get('normalized_entities', {})
        items = entities.get('items', [])

        if items:
            item = items[0]
            product_id = item.get('product_id')
            product_name = item.get('resolved_name', '')

            if product_id == expected_product_id and expected_product_keyword in product_name:
                return True, product_id, product_name
            else:
                return False, product_id, product_name
        else:
            return False, None, "No items resolved"

    except Exception as e:
        return False, None, str(e)


def main():
    """Test various message patterns."""

    # Test cases: (message, expected_product_id, expected_keyword)
    test_cases = [
        # Gold bracelets (ID: 3)
        ("acabo de vender 20 doradas", 3, "Dorada"),
        ("vendi 5 doradas", 3, "Dorada"),
        ("registrame venta de 10 pulseras doradas", 3, "Dorada"),
        ("venta de 3 gold", 3, "Dorada"),

        # Black bracelets (ID: 2)
        ("acabo de vender 15 negras", 2, "Negra"),
        ("vendi 8 negras", 2, "Negra"),
        ("registrame venta de 12 pulseras negras", 2, "Negra"),
        ("venta de 5 black", 2, "Negra"),

        # Classic bracelets (ID: 1)
        ("acabo de vender 7 clasicas", 1, "Cl"),  # "Clásica" or "Clasica"
        ("vendi 3 clasicas", 1, "Cl"),
        ("registrame venta de 9 pulseras clasicas", 1, "Cl"),
    ]

    print("Testing various user message patterns:")
    print("=" * 100)

    passed = 0
    failed = 0

    for message, expected_id, expected_keyword in test_cases:
        success, actual_id, actual_name = test_message(message, expected_id, expected_keyword)

        if success:
            status = "[PASS]"
            passed += 1
        else:
            status = "[FAIL]"
            failed += 1

        print(f"{status} Message: '{message}'")
        print(f"        Expected: ID {expected_id} with '{expected_keyword}'")
        print(f"        Got:      ID {actual_id}, Name: {actual_name}")
        print()

    print("=" * 100)
    print(f"\nResults: {passed} passed, {failed} failed out of {len(test_cases)} tests")

    return failed == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
