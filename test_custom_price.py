"""
Test custom price extraction.
"""
from agents import create_router_agent
from llm import get_llm
import json


def test_custom_prices():
    llm = get_llm()
    router = create_router_agent(llm)

    test_cases = [
        "registrame una venta de 1 pulsera negra a 5 dolares",
        "vendí 3 pulseras black a $10 cada una",
        "register sale of 2 classic bracelets at $8 each",
        "registrame 5 pulseras a 15 dólares",
    ]

    for test in test_cases:
        print("\n" + "="*70)
        print(f"Input: {test}")
        print("="*70)

        state = {
            "messages": [],
            "user_input": test,
            "normalized_entities": {}
        }

        result = router(state)

        print(f"\nIntent: {result.get('intent')}")
        print(f"Operation: {result.get('operation_type')}")
        print(f"\nEntities extracted:")
        entities = result.get('normalized_entities', {})
        print(json.dumps(entities, indent=2, ensure_ascii=False))

        # Check if unit_price was extracted
        if "items" in entities and entities["items"]:
            for i, item in enumerate(entities["items"]):
                if "unit_price" in item:
                    print(f"\n[OK] Custom price detected for item {i}: ${item['unit_price']}")
                else:
                    print(f"\n  No custom price for item {i} (will use catalog price)")


if __name__ == "__main__":
    test_custom_prices()
