"""
Test the resolver fix for product matching.
"""
import sys
sys.path.insert(0, '.')

# Import directly from database module
from database import fetch_one, fetch_all

# Copy the necessary functions from resolver
import unicodedata
import itertools

def normalize_text(text: str) -> str:
    """Normalize text for comparison (remove accents, lowercase)."""
    # Remove accents
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    return text.lower()

def generate_word_variations(word: str) -> list:
    """Generate variations of a word (plural/singular forms)."""
    variations = [word]
    if word.endswith('s') and len(word) > 2:
        variations.append(word[:-1])
    elif not word.endswith('s'):
        variations.append(word + 's')
    return variations

def translate_product_terms(text: str) -> list:
    """Generate variations of product names with translations."""
    variations = []
    seen = set()

    def add_variation(variation: str):
        if variation not in seen:
            seen.add(variation)
            variations.append(variation)

    add_variation(text)

    translations = {
        "black": "negra",
        "negra": "black",
        "gold": "dorada",
        "dorada": "gold",
        "classic": "clasica",
        "clasica": "classic",
        "clásica": "classic",
        "bracelet": "pulsera",
        "pulsera": "bracelet",
        "keychain": "llavero",
        "llavero": "keychain",
    }

    words = text.lower().split()
    for i, word in enumerate(words):
        if word in translations:
            new_words = words.copy()
            new_words[i] = translations[word]
            add_variation(" ".join(new_words))

    for original, translation in translations.items():
        if original in text.lower():
            add_variation(text.lower().replace(original, translation))

    return variations

def resolve_product_reference(item: dict) -> dict:
    """Resolve product reference to product_id (simplified test version)."""
    if "product_id" in item:
        return item

    product_ref = item.get("product_ref") or item.get("sku")
    if not product_ref:
        return item

    # Try exact SKU match first
    row = fetch_one(
        "SELECT id, sku, name FROM products WHERE sku = ?",
        (product_ref,)
    )

    # If not found, try partial name match with translations
    if not row:
        variations = translate_product_terms(product_ref)

        for variation in variations:
            words = variation.lower().split()

            # Try matching with all words (AND logic)
            if len(words) > 1:
                word_variations_list = []
                for word in words:
                    if word in ["de", "granos", "cafe", "con", "la", "el", "coffee", "bean", "beans"]:
                        continue
                    word_variations_list.append(generate_word_variations(word))

                for word_combo in itertools.product(*word_variations_list):
                    conditions = []
                    params = []

                    for word in word_combo:
                        conditions.append("REPLACE(REPLACE(REPLACE(REPLACE(LOWER(name), 'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o') LIKE ?")
                        params.append(f"%{normalize_text(word)}%")

                    if conditions:
                        query = f"""
                            SELECT id, sku, name FROM products
                            WHERE {' AND '.join(conditions)}
                            LIMIT 1
                            """
                        row = fetch_one(query, tuple(params))
                        if row:
                            break

                    if row:
                        break

            # If still not found, try individual words BUT rank by match count
            if not row:
                all_products = fetch_all("SELECT id, sku, name FROM products WHERE is_active = 1")
                best_match = None
                best_score = 0

                for product in all_products:
                    product_name_norm = normalize_text(product["name"])
                    score = 0

                    for word in words:
                        if word in ["de", "granos", "cafe", "con", "la", "el", "coffee", "bean", "beans"]:
                            continue

                        word_variations = generate_word_variations(word)
                        for word_var in word_variations:
                            if normalize_text(word_var) in product_name_norm:
                                score += 1
                                break

                    if score > best_score:
                        best_score = score
                        best_match = product

                if best_match and best_score > 0:
                    row = best_match

            if row:
                break

    if row:
        return {
            **item,
            "product_id": row["id"],
            "resolved_sku": row["sku"],
            "resolved_name": row["name"]
        }

    return {
        **item,
        "resolution_error": f"Product not found: {product_ref}"
    }

def test_product_resolution():
    """Test that products are resolved correctly with multiple words."""

    test_cases = [
        {
            "input": "pulsera dorada",
            "expected_sku": "BC-BRACELET-GOLD",
            "expected_name": "Pulsera de Granos de Café - Dorada"
        },
        {
            "input": "pulsera negra",
            "expected_sku": "BC-BRACELET-BLACK",
            "expected_name": "Pulsera de Granos de Café - Negra"
        },
        {
            "input": "pulsera clasica",
            "expected_sku": "BC-BRACELET-CLASSIC",
            "expected_name": "Pulsera de Granos de Café - Clásica"
        },
        {
            "input": "pulsera",
            "expected_sku": None,  # Ambiguous, could be any
            "expected_name": None
        },
    ]

    print("="*60)
    print("Testing Product Resolver")
    print("="*60)

    passed = 0
    failed = 0

    for test in test_cases:
        input_text = test["input"]
        expected_sku = test["expected_sku"]
        expected_name = test["expected_name"]

        item = {"product_ref": input_text}
        result = resolve_product_reference(item)

        resolved_sku = result.get("resolved_sku")
        resolved_name = result.get("resolved_name")

        print(f"\nInput: \"{input_text}\"")
        print(f"  Expected: {expected_name} ({expected_sku})")
        print(f"  Got:      {resolved_name} ({resolved_sku})")

        if expected_sku is None:
            # Ambiguous case - just check that it found something
            if "product_id" in result:
                print(f"  Status: [OK] PASS (found a match, though ambiguous)")
                passed += 1
            else:
                print(f"  Status: [FAIL] (no match found)")
                failed += 1
        else:
            if resolved_sku == expected_sku and expected_name in (resolved_name or ""):
                print(f"  Status: [OK] PASS")
                passed += 1
            else:
                print(f"  Status: [FAIL]")
                failed += 1

    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)

    return failed == 0


if __name__ == "__main__":
    success = test_product_resolution()
    exit(0 if success else 1)
