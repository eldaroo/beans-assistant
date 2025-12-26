"""
Debug single resolver case.
"""
from agents.resolver import resolve_product_reference, translate_product_terms, normalize_text


# Test "pulsera negra"
item = {"product_ref": "pulsera negra", "quantity": 1}

print("Testing: pulsera negra")
print("="*70)

variations = translate_product_terms("pulsera negra")
print(f"\nVariations generated: {variations}")

for var in variations:
    words = var.lower().split()
    print(f"\nVariation: {var}")
    print(f"  Words: {words}")

    filtered_words = [w for w in words if w not in ["de", "granos", "cafe", "con", "la", "el", "coffee", "bean", "beans"]]
    print(f"  Filtered: {filtered_words}")

    for word in filtered_words:
        print(f"    Normalized '{word}': {normalize_text(word)}")

print("\n" + "="*70)
print("Result:")
print("="*70)

result = resolve_product_reference(item)
print(result)
