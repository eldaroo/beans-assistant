"""
Script de debug para ver qué extrae el router.
"""
from agents import create_router_agent
from llm import get_llm
import json


def test_router():
    llm = get_llm()
    router = create_router_agent(llm)

    test_cases = [
        "registra venta de 1 pulsera negra",
        "vendí 2 pulseras black",
        "registrame una venta de 5 pulseras clásicas",
        "register sale of 3 black bracelets",
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
        print(f"Confidence: {result.get('confidence')}")
        print(f"\nEntities extracted:")
        print(json.dumps(result.get('normalized_entities', {}), indent=2, ensure_ascii=False))
        print(f"\nMissing fields: {result.get('missing_fields', [])}")


if __name__ == "__main__":
    test_router()
