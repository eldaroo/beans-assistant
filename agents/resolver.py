"""
Normalization/Resolver Agent - Resolves human references to concrete entities.

Responsibilities:
- Resolve product references ("pulseras negras" → SKU/product_id)
- Normalize dates ("ayer" → specific date)
- Resolve relative references ("la más barata" → query)
- Can perform simple reads to assist Write or Read agents
- NO writes
- NO final decisions
"""
from typing import Dict, Any
from datetime import datetime, timedelta
from database import fetch_one, fetch_all

from .state import AgentState


def extract_from_context(user_input: str, field_name: str) -> Any:
    """
    Try to extract missing field from conversation context or current message.

    Args:
        user_input: Full user input including context
        field_name: Field to extract (e.g., 'name', 'unit_price')

    Returns:
        Extracted value or None
    """
    import re

    # Extract both context and current message
    if "Mensaje actual:" in user_input:
        parts = user_input.split("Mensaje actual:")
        context_section = parts[0]
        current_message = parts[1] if len(parts) > 1 else ""
    else:
        context_section = ""
        current_message = user_input

    # Search in BOTH context and current message
    search_text = user_input  # Search in everything

    # Look for product names
    if field_name == "name":
        # Common patterns for product names
        patterns = [
            r'llamo\s+([^.\n]+)',
            r'registrar\s+(?:un nuevo tipo de\s+)?([^.\n,]+)',
            r'crear\s+([^.\n,]+)',
            r'producto\s+([^.\n,]+)',
            r'son\s+(?:unas?\s+)?([^.\n,]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, search_text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Clean up common words
                name = name.replace("nuevo tipo de", "").replace("unas", "").replace("las", "").replace("unos", "").strip()
                if name and len(name) > 3:
                    return name

    # Look for prices - search in BOTH context and current message
    elif field_name == "unit_price":
        # First try current message (most likely location)
        patterns = [
            r'^\s*(\d+(?:\.\d+)?)\s*(?:dolar|dollar|usd|pesos)',  # Just "10 dolares"
            r'\$\s*(\d+(?:\.\d+)?)',  # $10
            r'precio.*?\$?\s*(\d+(?:\.\d+)?)',
            r'vend.*?\$?\s*(\d+(?:\.\d+)?)',
            r'sal.*?\$?\s*(\d+(?:\.\d+)?)',
            r'cuesta.*?\$?\s*(\d+(?:\.\d+)?)',
        ]

        # Try current message first
        for pattern in patterns:
            match = re.search(pattern, current_message, re.IGNORECASE)
            if match:
                return float(match.group(1))

        # If not found in current message, try context
        for pattern in patterns:
            match = re.search(pattern, context_section, re.IGNORECASE)
            if match:
                return float(match.group(1))

    return None


def create_resolver_agent(llm=None):
    """
    Create the resolver agent that normalizes entities.

    This agent uses simple database lookups and rule-based logic
    to resolve human references to concrete values.

    Optionally uses LLM (Haiku) for disambiguation when needed.

    Args:
        llm: Optional language model for ambiguous cases (Haiku recommended)

    Returns:
        Agent function that resolves entities
    """

    def resolve_entities(state: AgentState) -> Dict[str, Any]:
        """
        Resolve human references to concrete database entities.

        Args:
            state: Current agent state with normalized_entities

        Returns:
            Updated state with fully resolved entities
        """
        entities = state.get("normalized_entities", {})
        operation_type = state.get("operation_type")
        user_input = state.get("user_input", "")

        try:
            resolved = {}
            variant_hints = detect_variant_hints(user_input)

            # Resolve product references
            if "items" in entities:
                resolved_items = []
                for item in entities["items"]:
                    item_with_hint = apply_variant_hint(item, variant_hints)

                    # Use hybrid resolution if LLM is available
                    if llm:
                        resolved_item = resolve_product_reference_hybrid(item_with_hint, llm)
                    else:
                        resolved_item = resolve_product_reference(item_with_hint)

                    resolved_item = enforce_variant_alignment(
                        item_with_hint, resolved_item, variant_hints
                    )

                    # Convert unit_price (USD) to unit_price_cents if present
                    if "unit_price" in resolved_item:
                        price_usd = resolved_item["unit_price"]
                        if isinstance(price_usd, (int, float)):
                            resolved_item["unit_price_cents"] = int(price_usd * 100)
                            # Remove the USD version
                            del resolved_item["unit_price"]

                    resolved_items.append(resolved_item)
                resolved["items"] = resolved_items

            # Resolve product_ref at top level (for ADD_STOCK, etc.)
            if "product_ref" in entities or "sku" in entities:
                # Create a temporary item dict for resolution
                temp_item = {
                    "product_ref": entities.get("product_ref") or entities.get("sku")
                }

                # Use hybrid resolution if LLM is available
                if llm:
                    resolved_item = resolve_product_reference_hybrid(temp_item, llm)
                else:
                    resolved_item = resolve_product_reference(temp_item)

                # Extract product_id from resolved item
                if "product_id" in resolved_item:
                    resolved["product_id"] = resolved_item["product_id"]
                    resolved["resolved_sku"] = resolved_item.get("resolved_sku")
                    resolved["resolved_name"] = resolved_item.get("resolved_name")
                elif "resolution_error" in resolved_item:
                    resolved["resolution_error"] = resolved_item["resolution_error"]

            # Resolve date references
            if "date" in entities:
                resolved["date"] = resolve_date(entities["date"])

            # Resolve amount (convert to cents if needed)
            if "amount" in entities:
                amount = entities["amount"]
                if isinstance(amount, (int, float)):
                    resolved["amount_cents"] = int(amount * 100)
                else:
                    resolved["amount_cents"] = entities.get("amount_cents")

            # Copy other entities as-is
            for key, value in entities.items():
                if key not in resolved:
                    resolved[key] = value

            # Convert unit_price to unit_price_cents if needed (BEFORE validation)
            if "unit_price" in resolved and "unit_price_cents" not in resolved:
                resolved["unit_price_cents"] = int(resolved["unit_price"] * 100)

            # Convert amount to amount_cents if needed
            if "amount" in resolved and "amount_cents" not in resolved:
                resolved["amount_cents"] = int(resolved["amount"] * 100)

            # Validate required fields based on operation type
            missing_fields = validate_required_fields(operation_type, resolved)

            # Try to extract missing fields from conversation context
            if missing_fields and user_input:
                for field in missing_fields[:]:  # Use slice to iterate over copy
                    value = extract_from_context(user_input, field)
                    if value:
                        resolved[field] = value
                        missing_fields.remove(field)

                # Convert any newly found prices to cents
                if "unit_price" in resolved and "unit_price_cents" not in resolved:
                    resolved["unit_price_cents"] = int(resolved["unit_price"] * 100)

            return {
                "normalized_entities": resolved,
                "missing_fields": missing_fields,
                "messages": [{
                    "role": "assistant",
                    "content": f"[Resolver] Resolved entities: {len(resolved)} fields"
                }]
            }

        except Exception as e:
            error_msg = f"Resolver error: {str(e)}"
            return {
                "error": error_msg,
                "messages": [{
                    "role": "assistant",
                    "content": f"[Resolver] {error_msg}"
                }]
            }

    return resolve_entities


def normalize_text(text: str) -> str:
    """Normalize text for comparison (remove accents, lowercase)."""
    import unicodedata
    # Remove accents
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    return text.lower()


def generate_word_variations(word: str) -> list[str]:
    """
    Generate variations of a word (plural/singular forms).

    Args:
        word: Original word

    Returns:
        List of variations
    """
    variations = [word]

    # Handle plural → singular (remove trailing 's')
    if word.endswith('s') and len(word) > 2:
        variations.append(word[:-1])

    # Handle singular → plural (add trailing 's')
    elif not word.endswith('s'):
        variations.append(word + 's')

    return variations


def translate_product_terms(text: str) -> list[str]:
    """
    Generate variations of product names with translations.

    Args:
        text: Original product reference

    Returns:
        List of variations to try
    """
    variations = []
    seen = set()

    def add_variation(variation: str):
        if variation not in seen:
            seen.add(variation)
            variations.append(variation)

    add_variation(text)

    # Translation mappings (both directions)
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

    # Generate variations with translations
    words = text.lower().split()
    for i, word in enumerate(words):
        if word in translations:
            new_words = words.copy()
            new_words[i] = translations[word]
            add_variation(" ".join(new_words))

    # Also try just translating individual words without context
    for original, translation in translations.items():
        if original in text.lower():
            add_variation(text.lower().replace(original, translation))

    return variations


VARIANT_HINT_TOKENS = {
    "dorada": ["dorad", "gold"],
    "negra": ["negr", "black"],
    "clasica": ["clasic"],
}


def detect_variant_hints(text: str) -> set[str]:
    """Detect variant hints (dorada/negra/clasica) from the user text."""
    normalized = normalize_text(text)
    hints = set()
    for variant, tokens in VARIANT_HINT_TOKENS.items():
        if any(token in normalized for token in tokens):
            hints.add(variant)
    return hints


def apply_variant_hint(item: Dict[str, Any], variant_hints: set[str]) -> Dict[str, Any]:
    """
    Append a hinted variant to the product_ref when the LLM missed it.

    IMPORTANT: Only applies a variant hint if the product_ref doesn't already
    have ANY variant specified. This prevents adding multiple variants to a
    single item when processing multi-item commands like "400 clasicas y 200 doradas".
    """
    if not variant_hints:
        return item

    product_ref = item.get("product_ref") or item.get("sku")
    if not product_ref:
        return item

    ref_normalized = normalize_text(product_ref)

    # Check if product_ref already has ANY variant
    has_any_variant = any(
        variant in ref_normalized or any(token in ref_normalized for token in tokens)
        for variant, tokens in VARIANT_HINT_TOKENS.items()
    )

    # If it already has a variant, don't add another one
    if has_any_variant:
        return item

    # If no variant found, apply the first matching hint
    for variant, tokens in VARIANT_HINT_TOKENS.items():
        if variant in variant_hints:
            new_ref = f"{product_ref} {variant}".strip()
            return {**item, "product_ref": new_ref}

    return item


def enforce_variant_alignment(
    original_item: Dict[str, Any],
    resolved_item: Dict[str, Any],
    variant_hints: set[str],
) -> Dict[str, Any]:
    """
    If a variant is hinted in the text but the resolved product disagrees,
    retry resolution with the hinted variant appended.
    """
    if not variant_hints:
        return resolved_item

    resolved_name_norm = normalize_text(resolved_item.get("resolved_name", ""))
    if "product_id" in resolved_item and any(
        variant in resolved_name_norm for variant in variant_hints
    ):
        return resolved_item

    base_ref = original_item.get("product_ref") or original_item.get("sku") or ""
    for variant in variant_hints:
        retry_ref = f"{base_ref} {variant}".strip()
        retry_item = {**original_item, "product_ref": retry_ref}
        retry_result = resolve_product_reference(retry_item)
        retry_name_norm = normalize_text(retry_result.get("resolved_name", ""))
        if "product_id" in retry_result and variant in retry_name_norm:
            return retry_result

    return resolved_item


def resolve_product_reference(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve product reference to product_id.

    Args:
        item: Item dict with product_ref or sku

    Returns:
        Item dict with product_id resolved
    """
    # If already has product_id, return as-is
    if "product_id" in item:
        return item

    # Get product reference
    product_ref = item.get("product_ref") or item.get("sku")
    if not product_ref:
        return item

    # Query database for matching product
    # Try exact SKU match first
    row = fetch_one(
        "SELECT id, sku, name FROM products WHERE sku = ?",
        (product_ref,)
    )

    # If not found, try partial name match with translations
    if not row:
        # Get all variations (with translations)
        variations = translate_product_terms(product_ref)

        for variation in variations:
            # Split search term into words for better matching
            words = variation.lower().split()

            # Try matching with all words (AND logic) - using normalized text
            if len(words) > 1:
                # Build query with multiple LIKE conditions (accent-insensitive)
                # We normalize both the search term and the database field
                # Try all combinations of word variations (singular/plural)

                # Get variations for each word
                word_variations_list = []
                for word in words:
                    # Skip common words
                    if word in ["de", "granos", "cafe", "con", "la", "el", "coffee", "bean", "beans"]:
                        continue
                    word_variations_list.append(generate_word_variations(word))

                # Try different combinations
                import itertools
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
                        # Debug
                        # print(f"DEBUG Query: {query}")
                        # print(f"DEBUG Params: {params}")

                        row = fetch_one(query, tuple(params))
                        if row:
                            break

                    if row:
                        break

            # If still not found, try individual words BUT rank by match count
            if not row:
                # print(f"DEBUG: Multi-word search failed, trying individual words with ranking")

                # Get all products
                all_products = fetch_all("SELECT id, sku, name FROM products WHERE is_active = 1")

                # Score each product by how many words match
                best_match = None
                best_score = 0
                total_meaningful_words = 0

                # Count how many meaningful words the user provided
                for word in words:
                    if word not in ["de", "granos", "cafe", "con", "la", "el", "coffee", "bean", "beans", "pulsera", "pulseras", "bracelet"]:
                        total_meaningful_words += 1

                for product in all_products:
                    product_name_norm = normalize_text(product["name"])
                    score = 0

                    # Count how many input words appear in this product name
                    for word in words:
                        # Skip common words
                        if word in ["de", "granos", "cafe", "con", "la", "el", "coffee", "bean", "beans"]:
                            continue

                        # Check word variations (singular/plural)
                        word_variations = generate_word_variations(word)
                        for word_var in word_variations:
                            if normalize_text(word_var) in product_name_norm:
                                score += 1
                                break  # Don't double-count the same word

                    # Update best match if this product scores higher
                    if score > best_score:
                        best_score = score
                        best_match = product

                # CRITICAL SAFETY CHECK: Only accept match if we matched ALL meaningful words
                # If user said specific descriptors (like "arcoiris"), we MUST match them
                # Don't accept matches based only on generic words like "pulsera"
                if best_match and best_score > 0:
                    # Require that ALL meaningful words were matched
                    if total_meaningful_words > 0 and best_score >= total_meaningful_words:
                        row = best_match
                        # print(f"DEBUG: Best match with score {best_score}/{total_meaningful_words}: {row['name']}")
                    # If user only said generic words (total_meaningful_words == 0), DON'T guess
                    # This forces users to be specific when there are multiple products
                    # Otherwise: Don't match - user needs to be more specific

            if row:
                break

    if row:
        return {
            **item,
            "product_id": row["id"],
            "resolved_sku": row["sku"],
            "resolved_name": row["name"]
        }

    # If still not found, return original with error flag
    # Get all active products to show in error message
    all_products = fetch_all("SELECT sku, name FROM products WHERE is_active = 1 ORDER BY name")
    available_list = ", ".join([f"{p['name']}" for p in all_products])

    # Check if user input was too generic (no specific variant/color mentioned)
    normalized_ref = normalize_text(product_ref)
    if any(generic in normalized_ref for generic in ["pulsera", "bracelet", "llavero", "keychain"]):
        # User said something generic - tell them to be more specific
        return {
            **item,
            "resolution_error": f"Por favor especificá cuál producto querés. Productos disponibles: {available_list}"
        }
    else:
        # User said something specific that doesn't exist
        return {
            **item,
            "resolution_error": f"Producto '{product_ref}' no encontrado. Productos disponibles: {available_list}"
        }


def resolve_product_reference_hybrid(item: Dict[str, Any], llm) -> Dict[str, Any]:
    """
    Hybrid product resolution using deterministic matching + LLM fallback.

    Strategy:
    1. If exact match or high-confidence (>90%) → use deterministic (FAST, FREE)
    2. If no match or low confidence → use LLM Haiku (SMART, CHEAP)
    3. If multiple similar candidates → use LLM to disambiguate

    Args:
        item: Item dict with product_ref or sku
        llm: Language model instance (Haiku)

    Returns:
        Item dict with product_id resolved
    """
    # If already has product_id, return as-is
    if "product_id" in item:
        return item

    # Get product reference
    product_ref = item.get("product_ref") or item.get("sku")
    if not product_ref:
        return item

    # Get all candidates with scores
    candidates = fuzzy_match_with_scores(product_ref)

    # Decision logic based on confidence
    if len(candidates) == 0:
        # No matches found → fallback to original error handling
        print(f"[Hybrid Resolver] No candidates found for '{product_ref}'")
        return resolve_product_reference(item)  # Use original function for error message

    elif len(candidates) == 1 and candidates[0]["score"] >= 0.9:
        # Single high-confidence match → deterministic (FAST, FREE)
        print(f"[Hybrid Resolver] High confidence match: {candidates[0]['name']} ({candidates[0]['score']:.0%})")
        return {
            **item,
            "product_id": candidates[0]["id"],
            "resolved_sku": candidates[0]["sku"],
            "resolved_name": candidates[0]["name"]
        }

    elif len(candidates) == 1 and candidates[0]["score"] < 0.9:
        # Single low-confidence match → use LLM to verify
        print(f"[Hybrid Resolver] Low confidence ({candidates[0]['score']:.0%}), asking LLM to verify")
        result = llm_disambiguate_product(product_ref, candidates, llm)
        return {**item, **result}

    else:
        # Multiple candidates → use LLM to disambiguate
        top_scores = [c["score"] for c in candidates[:3]]
        print(f"[Hybrid Resolver] Multiple candidates (top scores: {top_scores}), asking LLM")
        result = llm_disambiguate_product(product_ref, candidates, llm)
        return {**item, **result}


def fuzzy_match_with_scores(product_ref: str) -> list:
    """
    Find all matching products with confidence scores.

    Args:
        product_ref: Product reference to match

    Returns:
        List of dicts with keys: id, sku, name, score (0-1)
    """
    # Try exact SKU match first
    row = fetch_one(
        "SELECT id, sku, name FROM products WHERE sku = ?",
        (product_ref,)
    )

    if row:
        return [{
            "id": row["id"],
            "sku": row["sku"],
            "name": row["name"],
            "score": 1.0  # Exact SKU match = 100% confidence
        }]

    # Get all active products for fuzzy matching
    all_products = fetch_all("SELECT id, sku, name FROM products WHERE is_active = 1")

    # Get variations with translations
    variations = translate_product_terms(product_ref)

    candidates = []

    for variation in variations:
        words = variation.lower().split()
        total_meaningful_words = sum(
            1 for word in words
            if word not in ["de", "granos", "cafe", "con", "la", "el", "coffee", "bean", "beans", "pulsera", "pulseras", "bracelet"]
        )

        for product in all_products:
            product_name_norm = normalize_text(product["name"])
            score = 0

            # Count matching words
            for word in words:
                if word in ["de", "granos", "cafe", "con", "la", "el", "coffee", "bean", "beans"]:
                    continue

                word_variations = generate_word_variations(word)
                for word_var in word_variations:
                    if normalize_text(word_var) in product_name_norm:
                        score += 1
                        break

            # Calculate confidence score
            if total_meaningful_words > 0:
                confidence = score / total_meaningful_words

                if confidence > 0:
                    # Check if already in candidates
                    existing = next((c for c in candidates if c["id"] == product["id"]), None)
                    if existing:
                        # Update if better score
                        if confidence > existing["score"]:
                            existing["score"] = confidence
                    else:
                        candidates.append({
                            "id": product["id"],
                            "sku": product["sku"],
                            "name": product["name"],
                            "score": confidence
                        })

    # Sort by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)

    return candidates


def llm_disambiguate_product(product_ref: str, candidates: list, llm) -> Dict[str, Any]:
    """
    Use LLM to disambiguate between multiple product candidates.

    Args:
        product_ref: User's product reference
        candidates: List of candidate products with scores
        llm: Language model instance (Haiku)

    Returns:
        Dict with resolved product_id, sku, name
    """
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import JsonOutputParser
    from pydantic import BaseModel, Field

    class ProductChoice(BaseModel):
        product_id: int = Field(description="ID of the chosen product")
        reasoning: str = Field(description="Why this product was chosen")

    # Build candidates list for prompt
    candidates_str = "\n".join([
        f"- ID {c['id']}: {c['name']} (SKU: {c['sku']}, confidence: {c['score']:.0%})"
        for c in candidates[:5]  # Top 5 only
    ])

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a product disambiguation assistant.

The user asked for: "{product_ref}"

We found these possible matches:
{candidates}

Choose the MOST LIKELY product the user meant. Consider:
- Exact word matches (colors, variants)
- Confidence scores
- Context clues in the user's query

Return JSON with product_id and reasoning."""),
        ("user", "Which product did the user mean?")
    ])

    parser = JsonOutputParser(pydantic_object=ProductChoice)
    chain = prompt | llm | parser

    try:
        result = chain.invoke({
            "product_ref": product_ref,
            "candidates": candidates_str
        })

        # Find the chosen candidate
        chosen = next((c for c in candidates if c["id"] == result["product_id"]), None)

        if chosen:
            print(f"[LLM Disambiguate] Chose '{chosen['name']}' - Reasoning: {result['reasoning']}")
            return {
                "product_id": chosen["id"],
                "resolved_sku": chosen["sku"],
                "resolved_name": chosen["name"],
                "llm_used": True
            }

    except Exception as e:
        print(f"[LLM Disambiguate] Failed: {e}")

    # Fallback: return highest scoring candidate
    if candidates:
        return {
            "product_id": candidates[0]["id"],
            "resolved_sku": candidates[0]["sku"],
            "resolved_name": candidates[0]["name"],
            "llm_used": False
        }

    return {"resolution_error": f"No se pudo resolver '{product_ref}'"}


def resolve_date(date_ref: str) -> str:
    """
    Resolve date reference to ISO date string.

    Args:
        date_ref: Date reference ("ayer", "yesterday", "2024-01-15", etc.)

    Returns:
        ISO date string (YYYY-MM-DD)
    """
    date_ref_lower = date_ref.lower().strip()

    # Handle relative dates
    today = datetime.now().date()

    if date_ref_lower in ["hoy", "today"]:
        return today.isoformat()
    elif date_ref_lower in ["ayer", "yesterday"]:
        return (today - timedelta(days=1)).isoformat()
    elif date_ref_lower in ["anteayer", "day before yesterday"]:
        return (today - timedelta(days=2)).isoformat()

    # Try to parse as ISO date
    try:
        parsed = datetime.fromisoformat(date_ref)
        return parsed.date().isoformat()
    except ValueError:
        pass

    # Default: return as-is
    return date_ref


def generate_sku_from_name(name: str) -> str:
    """
    Generate SKU automatically from ANY product name without hardcoded mappings.

    Strategy:
    - Extract product type (pulsera, llavero, etc.)
    - Extract descriptive words (color, size, name, etc.)
    - Build SKU: BC-{TYPE}-{DESCRIPTORS}
    - Deduplicate if needed

    Examples:
        "Pulseras Fuccias" → "BC-PULS-FUCCIAS"
        "Pulseras Grandes Negras" → "BC-PULS-GRANDES-NEGRAS"
        "Llavero María" → "BC-LLAV-MARIA"
        "Pulseras Premium Arcoíris" → "BC-PULS-PREMIUM-ARCOIRIS"
        "Pulseras Celestes XL" → "BC-PULS-CELESTES-XL"

    Args:
        name: Product name (any descriptive name)

    Returns:
        Generated SKU (unique, descriptive, max 30 chars)
    """
    # Normalize and extract key words
    normalized = normalize_text(name)
    words = normalized.split()

    # Mapping of product types (ONLY types, not colors!)
    type_mapping = {
        "pulsera": "PULS",
        "pulseras": "PULS",
        "bracelet": "PULS",
        "bracelets": "PULS",
        "llavero": "LLAV",
        "llaveros": "LLAV",
        "keychain": "LLAV",
        "keychains": "LLAV",
    }

    # Common filler words to skip (don't add value to SKU)
    skip_words = {
        "de", "del", "la", "las", "el", "los",  # Articles
        "granos", "cafe", "coffee", "bean", "beans",  # Generic coffee words
        "con", "y", "e", "and",  # Connectors
    }

    # Extract type and descriptive words
    product_type = None
    descriptors = []

    for word in words:
        if word in type_mapping and not product_type:
            product_type = type_mapping[word]
        elif word not in skip_words and len(word) > 1:  # Skip single letters
            # Keep as descriptor (color, size, name, etc.)
            descriptors.append(word.upper())

    # Build SKU
    if not product_type:
        product_type = "PROD"  # Generic product

    if descriptors:
        # Use first 2 descriptors to keep SKU readable
        # Limit each descriptor to 10 chars to avoid huge SKUs
        desc_parts = [d[:10] for d in descriptors[:2]]
        desc_part = "-".join(desc_parts)
        base_sku = f"BC-{product_type}-{desc_part}"
    else:
        base_sku = f"BC-{product_type}-STD"

    # Check if SKU already exists and make it unique if needed
    from database import fetch_one
    existing = fetch_one("SELECT sku FROM products WHERE sku = ?", (base_sku,))

    if existing:
        # SKU exists, append a number to make it unique
        print(f"[SKU Generation] SKU '{base_sku}' already exists, generating unique SKU...")
        counter = 2
        while True:
            new_sku = f"{base_sku}-{counter}"
            existing = fetch_one("SELECT sku FROM products WHERE sku = ?", (new_sku,))
            if not existing:
                print(f"[SKU Generation] Generated unique SKU: {new_sku}")
                return new_sku
            counter += 1
    else:
        print(f"[SKU Generation] Generated SKU: {base_sku} (from name: '{name}')")

    return base_sku


def validate_required_fields(operation_type: str, entities: Dict[str, Any]) -> list[str]:
    """
    Validate that all required fields are present for the operation.

    Args:
        operation_type: Type of operation
        entities: Resolved entities

    Returns:
        List of missing required fields
    """
    missing = []

    if operation_type == "REGISTER_SALE":
        if "items" not in entities or not entities["items"]:
            missing.append("items")
        else:
            # Check each item has required fields
            for i, item in enumerate(entities["items"]):
                if "product_id" not in item and "resolution_error" in item:
                    missing.append(f"items[{i}].product_id (not found)")
                if "quantity" not in item:
                    missing.append(f"items[{i}].quantity")

    elif operation_type == "REGISTER_EXPENSE":
        if "amount_cents" not in entities:
            missing.append("amount")
        if "description" not in entities:
            missing.append("description")

    elif operation_type == "REGISTER_PRODUCT":
        # SKU is now auto-generated, so only check other required fields
        required = ["name", "unit_price_cents"]
        for field in required:
            if field not in entities:
                missing.append(field)

        # Auto-generate SKU if not provided
        if "sku" not in entities and "name" in entities:
            entities["sku"] = generate_sku_from_name(entities["name"])

        # Default unit_cost_cents to 0 if not provided
        if "unit_cost_cents" not in entities:
            entities["unit_cost_cents"] = 0

    elif operation_type == "ADD_STOCK":
        # ADD_STOCK can work with either:
        # 1. Single product: product_id + quantity
        # 2. Multiple products: items array (like REGISTER_SALE)
        has_single = "product_id" in entities and "quantity" in entities
        has_items = "items" in entities and len(entities.get("items", [])) > 0

        if not has_single and not has_items:
            # Need either single product OR items array
            if "items" not in entities:
                missing.append("product_id")
                missing.append("quantity")
            else:
                missing.append("items")

    elif operation_type == "DEACTIVATE_PRODUCT":
        # Need product_id (should be resolved from product_ref)
        if "product_id" not in entities:
            missing.append("product_id")

    return missing


def route_after_resolver(state: AgentState) -> str:
    """
    Determine next step after entity resolution.

    Args:
        state: Current agent state

    Returns:
        Name of next node
    """
    # If error or missing fields, go to final answer
    if state.get("error") or state.get("missing_fields"):
        return "final_answer"

    # Otherwise, go to write agent
    return "write_agent"
