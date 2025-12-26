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


def create_resolver_agent():
    """
    Create the resolver agent that normalizes entities.

    This agent uses simple database lookups and rule-based logic
    to resolve human references to concrete values.

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

            # Resolve product references
            if "items" in entities:
                resolved_items = []
                for item in entities["items"]:
                    resolved_item = resolve_product_reference(item)

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
    variations = [text]

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
            variations.append(" ".join(new_words))

    # Also try just translating individual words without context
    for original, translation in translations.items():
        if original in text.lower():
            variations.append(text.lower().replace(original, translation))

    return list(set(variations))  # Remove duplicates


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

            # If still not found, try individual words
            if not row:
                # print(f"DEBUG: Multi-word search failed, trying individual words")
                for word in words:
                    # Skip common words
                    if word in ["de", "granos", "cafe", "con", "la", "el", "coffee", "bean", "beans"]:
                        continue

                    # print(f"DEBUG: Searching for individual word: {word}")
                    row = fetch_one(
                        """
                        SELECT id, sku, name FROM products
                        WHERE REPLACE(REPLACE(REPLACE(REPLACE(LOWER(name), 'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o') LIKE ?
                        LIMIT 1
                        """,
                        (f"%{normalize_text(word)}%",)
                    )
                    if row:
                        # print(f"DEBUG: Found match with individual word: {row['name']}")
                        break

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
    return {
        **item,
        "resolution_error": f"Product not found: {product_ref}. Available products: BC-BRACELET-BLACK (Pulsera Negra), BC-BRACELET-CLASSIC (Pulsera Clásica), BC-BRACELET-GOLD (Pulsera Dorada), BC-KEYCHAIN (Llavero)"
    }


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
    Generate SKU automatically from product name.

    Args:
        name: Product name (e.g., "Pulseras Azules", "Llavero Rojo")

    Returns:
        Generated SKU (e.g., "BC-PULS-AZUL", "BC-LLAV-ROJO")
    """
    # Normalize and extract key words
    normalized = normalize_text(name)
    words = normalized.split()

    # Mapping of product types
    type_mapping = {
        "pulsera": "PULS",
        "pulseras": "PULS",
        "bracelet": "PULS",
        "llavero": "LLAV",
        "llaveros": "LLAV",
        "keychain": "LLAV",
    }

    # Color/variant mapping
    color_mapping = {
        "negra": "NEGRA",
        "negras": "NEGRA",
        "black": "NEGRA",
        "clasica": "CLASICA",
        "clasicas": "CLASICA",
        "classic": "CLASICA",
        "dorada": "DORADA",
        "doradas": "DORADA",
        "gold": "DORADA",
        "azul": "AZUL",
        "azules": "AZUL",
        "blue": "AZUL",
        "roja": "ROJA",
        "rojas": "ROJA",
        "red": "ROJA",
        "verde": "VERDE",
        "verdes": "VERDE",
        "green": "VERDE",
        "blanca": "BLANCA",
        "blancas": "BLANCA",
        "white": "BLANCA",
    }

    # Identify type and variant
    product_type = None
    variant = None

    for word in words:
        if word in type_mapping and not product_type:
            product_type = type_mapping[word]
        if word in color_mapping and not variant:
            variant = color_mapping[word]

    # Default values
    if not product_type:
        product_type = "PROD"  # Generic product
    if not variant:
        variant = "STD"  # Standard variant

    return f"BC-{product_type}-{variant}"


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
        if "product_id" not in entities:
            missing.append("product_id")
        if "quantity" not in entities:
            missing.append("quantity")

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
