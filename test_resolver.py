"""
Test script to verify product resolution works correctly.
"""
from agents.resolver import resolve_product_reference, detect_variant_hints, apply_variant_hint, enforce_variant_alignment
from database import fetch_all


def test_product_resolution():
    """Test that various product references resolve correctly."""

    # Get all products to show what's in the database
    products = fetch_all("SELECT id, sku, name FROM products")
    print("Available products:")
    for p in products:
        print(f"  {p['id']}: {p['sku']} - {p['name']}")
    print()

    # Test cases: (user input, expected product id, expected product name)
    test_cases = [
        ("doradas", 3, "Pulsera de Granos de Café - Dorada"),
        ("dorada", 3, "Pulsera de Granos de Café - Dorada"),
        ("pulseras doradas", 3, "Pulsera de Granos de Café - Dorada"),
        ("negras", 2, "Pulsera de Granos de Café - Negra"),
        ("negra", 2, "Pulsera de Granos de Café - Negra"),
        ("pulseras negras", 2, "Pulsera de Granos de Café - Negra"),
        ("clasicas", 1, "Pulsera de Granos de Café - Clásica"),
        ("clasica", 1, "Pulsera de Granos de Café - Clásica"),
        ("pulseras clasicas", 1, "Pulsera de Granos de Café - Clásica"),
        ("gold", 3, "Pulsera de Granos de Café - Dorada"),
        ("black", 2, "Pulsera de Granos de Café - Negra"),
    ]

    print("Testing product resolution:")
    print("-" * 80)

    failed_tests = []
    for user_input, expected_id, expected_name in test_cases:
        # Simulate the full resolution flow
        variant_hints = detect_variant_hints(user_input)

        # Create item dict
        item = {"product_ref": user_input, "quantity": 1}

        # Apply variant hint
        item_with_hint = apply_variant_hint(item, variant_hints)

        # Resolve
        resolved = resolve_product_reference(item_with_hint)

        # Enforce alignment
        final_resolved = enforce_variant_alignment(item_with_hint, resolved, variant_hints)

        # Check result
        if "product_id" in final_resolved:
            actual_id = final_resolved["product_id"]
            actual_name = final_resolved.get("resolved_name", "")
            status = "[PASS]" if actual_id == expected_id else "[FAIL]"

            if actual_id != expected_id:
                failed_tests.append((user_input, expected_id, actual_id))

            print(f"{status} | Input: '{user_input:20s}' | Expected ID: {expected_id} | Got ID: {actual_id} | Name: {actual_name}")
        else:
            error = final_resolved.get("resolution_error", "Unknown error")
            print(f"[FAIL] | Input: '{user_input:20s}' | Expected ID: {expected_id} | ERROR: {error}")
            failed_tests.append((user_input, expected_id, None))

    print("-" * 80)

    if failed_tests:
        print(f"\n[X] {len(failed_tests)} tests FAILED:")
        for user_input, expected, actual in failed_tests:
            print(f"  - '{user_input}': expected ID {expected}, got {actual}")
        return False
    else:
        print(f"\n[OK] All {len(test_cases)} tests PASSED!")
        return True


if __name__ == "__main__":
    success = test_product_resolution()
    exit(0 if success else 1)
