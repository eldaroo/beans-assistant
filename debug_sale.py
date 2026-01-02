"""
Debug script to see what's happening with sale processing.
"""
from graph import create_business_agent_graph
import json


def debug_sale(message):
    """Debug a sale message to see where it fails."""
    print("=" * 80)
    print(f"Testing message: '{message}'")
    print("=" * 80)

    graph = create_business_agent_graph()

    state = {
        "messages": [],
        "user_input": message,
        "normalized_entities": {}
    }

    try:
        result = graph.invoke(state)

        print("\n[RESULT DETAILS]")
        print("-" * 80)
        print(f"Intent: {result.get('intent')}")
        print(f"Operation Type: {result.get('operation_type')}")
        print(f"Confidence: {result.get('confidence')}")

        print("\n[NORMALIZED ENTITIES]")
        print("-" * 80)
        entities = result.get('normalized_entities', {})
        print(json.dumps(entities, indent=2, ensure_ascii=False))

        if 'items' in entities:
            print("\n[ITEMS RESOLVED]")
            print("-" * 80)
            for i, item in enumerate(entities['items']):
                print(f"\nItem {i + 1}:")
                print(f"  product_ref: {item.get('product_ref', 'N/A')}")
                print(f"  product_id: {item.get('product_id', 'N/A')}")
                print(f"  resolved_name: {item.get('resolved_name', 'N/A')}")
                print(f"  quantity: {item.get('quantity', 'N/A')}")
                if 'resolution_error' in item:
                    print(f"  [ERROR] {item['resolution_error']}")

        print("\n[FINAL ANSWER]")
        print("-" * 80)
        print(result.get('final_answer', 'No answer'))

        print("\n" + "=" * 80)

        return result

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Test cases
    test_messages = [
        "acabo de vender 200 pulseras doradas",
        "vendi 20 doradas",
        "venta de 10 pulseras doradas",
        "registrame venta de 5 doradas",
    ]

    for msg in test_messages:
        debug_sale(msg)
        print("\n\n")
