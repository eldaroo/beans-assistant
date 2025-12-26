"""
Test resolver functionality.
"""
from agents.resolver import resolve_product_reference


def test_resolver():
    test_cases = [
        {"product_ref": "pulsera negra", "quantity": 1},
        {"product_ref": "pulseras black", "quantity": 2},
        {"product_ref": "negra", "quantity": 1},
        {"product_ref": "black", "quantity": 1},
        {"product_ref": "dorada", "quantity": 1},
        {"product_ref": "clasica", "quantity": 1},
        {"product_ref": "BC-BRACELET-BLACK", "quantity": 1},
        {"product_ref": "llavero", "quantity": 1},
    ]

    for item in test_cases:
        print("\n" + "="*70)
        print(f"Input: {item}")
        print("="*70)

        result = resolve_product_reference(item)

        if "product_id" in result:
            print(f"FOUND")
            print(f"  Product ID: {result['product_id']}")
            print(f"  SKU: {result.get('resolved_sku')}")
            print(f"  Name: {result.get('resolved_name')}")
        else:
            print(f"NOT FOUND")
            if "resolution_error" in result:
                print(f"  Error: {result['resolution_error']}")


if __name__ == "__main__":
    test_resolver()
