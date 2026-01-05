"""
Unit tests for agents/resolver.py entity resolution.

Tests cover:
- Product reference resolution - exact matches (5 tests)
- Product reference resolution - fuzzy matches (8 tests)
- Variant hint detection and application (6 tests)
- Date resolution and field validation (6 tests)

Total: 25 tests
"""
import pytest
from datetime import datetime, timedelta
from agents.resolver import (
    resolve_product_reference,
    detect_variant_hints,
    apply_variant_hint,
    enforce_variant_alignment,
    resolve_date,
    validate_required_fields,
    normalize_text,
    generate_word_variations,
    translate_product_terms,
    generate_sku_from_name,
)


# ==============================================================================
# PRODUCT RESOLUTION - EXACT MATCHES (5 tests)
# ==============================================================================

@pytest.mark.unit
class TestProductResolutionExact:
    """Tests for exact product reference resolution."""

    def test_resolve_by_exact_sku(self, populated_db):
        """Test resolution by exact SKU match."""
        item = {"product_ref": "BC-BRACELET-BLACK", "quantity": 5}
        result = resolve_product_reference(item)

        assert result["product_id"] == 2
        assert result["resolved_sku"] == "BC-BRACELET-BLACK"
        assert "Negra" in result["resolved_name"]

    def test_resolve_by_exact_name(self, populated_db):
        """Test resolution by exact product name."""
        item = {"product_ref": "Pulsera de Granos de Café - Dorada", "quantity": 3}
        result = resolve_product_reference(item)

        assert result["product_id"] == 3
        assert "Dorada" in result["resolved_name"]

    def test_resolve_with_existing_product_id(self, populated_db):
        """Test that item with product_id already set is returned as-is."""
        item = {"product_id": 1, "quantity": 10}
        result = resolve_product_reference(item)

        # Should return unchanged since product_id already exists
        assert result["product_id"] == 1
        assert result["quantity"] == 10

    def test_resolve_nonexistent_product_returns_error(self, populated_db):
        """Test that nonexistent product returns resolution_error."""
        item = {"product_ref": "NonexistentProduct123", "quantity": 5}
        result = resolve_product_reference(item)

        assert "resolution_error" in result
        assert "NonexistentProduct123" in result["resolution_error"]
        assert "no encontrado" in result["resolution_error"].lower()  # Spanish error message

    def test_resolve_empty_reference_returns_original(self, populated_db):
        """Test that empty product_ref returns item as-is."""
        item = {"quantity": 5}
        result = resolve_product_reference(item)

        assert result == item
        assert "product_id" not in result


# ==============================================================================
# PRODUCT RESOLUTION - FUZZY MATCHES (8 tests)
# ==============================================================================

@pytest.mark.unit
class TestProductResolutionFuzzy:
    """Tests for fuzzy/partial product reference resolution."""

    def test_resolve_partial_name_match(self, populated_db):
        """Test that generic 'pulsera' requires specification (safety check)."""
        item = {"product_ref": "pulsera", "quantity": 1}
        result = resolve_product_reference(item)

        # After safety improvements, generic "pulsera" should require specification
        assert "resolution_error" in result
        assert "especific" in result["resolution_error"].lower()  # "Por favor especificá"

    def test_resolve_case_insensitive(self, populated_db):
        """Test that resolution is case-insensitive."""
        item1 = {"product_ref": "LLAVERO", "quantity": 1}
        item2 = {"product_ref": "llavero", "quantity": 1}
        item3 = {"product_ref": "Llavero", "quantity": 1}

        result1 = resolve_product_reference(item1)
        result2 = resolve_product_reference(item2)
        result3 = resolve_product_reference(item3)

        # All should resolve to the same keychain product (ID 4)
        assert result1["product_id"] == 4
        assert result2["product_id"] == 4
        assert result3["product_id"] == 4

    def test_resolve_accent_insensitive(self, populated_db):
        """Test that resolution handles accents in product names."""
        # Use "clasica" (without accent) to match "Clásica" (with accent)
        item = {"product_ref": "Pulsera Clasica", "quantity": 1}
        result = resolve_product_reference(item)

        assert "product_id" in result
        assert result["product_id"] == 1  # BC-BRACELET-CLASSIC
        assert "Clásica" in result["resolved_name"]

    def test_resolve_singular_plural_variations(self, populated_db):
        """Test that singular and plural forms resolve correctly."""
        item_singular = {"product_ref": "pulsera negra", "quantity": 1}
        item_plural = {"product_ref": "pulseras negras", "quantity": 1}

        result_singular = resolve_product_reference(item_singular)
        result_plural = resolve_product_reference(item_plural)

        # Both should resolve to same product
        assert result_singular["product_id"] == 2
        assert result_plural["product_id"] == 2

    def test_resolve_spanish_to_english_translation(self, populated_db):
        """Test resolution with English equivalent of Spanish variant."""
        item = {"product_ref": "black", "quantity": 1}
        result = resolve_product_reference(item)

        # "black" should resolve to "Negra" variant
        assert result["product_id"] == 2
        assert "Negra" in result["resolved_name"]

    def test_resolve_english_to_spanish_translation(self, populated_db):
        """Test resolution with Spanish equivalent of English variant."""
        item = {"product_ref": "gold", "quantity": 1}
        result = resolve_product_reference(item)

        # "gold" should resolve to "Dorada" variant
        assert result["product_id"] == 3
        assert "Dorada" in result["resolved_name"]

    def test_resolve_multi_word_product_all_words(self, populated_db):
        """Test resolution when all words of product name are provided."""
        item = {"product_ref": "pulsera dorada", "quantity": 1}
        result = resolve_product_reference(item)

        assert result["product_id"] == 3
        assert "Dorada" in result["resolved_name"]

    def test_resolve_multi_word_product_partial_words(self, populated_db):
        """Test resolution with multiple specific words (scoring system)."""
        # Use "granos negra" - specific enough to match uniquely
        item = {"product_ref": "granos negra", "quantity": 1}
        result = resolve_product_reference(item)

        # Should match the black bracelet (has both "granos" and "negra")
        assert "product_id" in result
        assert result["product_id"] == 2  # BC-BRACELET-BLACK
        assert "Negra" in result["resolved_name"]


# ==============================================================================
# VARIANT HINTS TESTS (6 tests)
# ==============================================================================

@pytest.mark.unit
class TestVariantHints:
    """Tests for variant hint detection and application."""

    def test_detect_variant_hints_dorada(self):
        """Test detection of 'dorada' variant hint."""
        hints = detect_variant_hints("vendí 20 pulseras doradas")
        assert "dorada" in hints

    def test_detect_variant_hints_negra(self):
        """Test detection of 'negra' variant hint."""
        hints = detect_variant_hints("entraron 50 negras")
        assert "negra" in hints

    def test_detect_variant_hints_clasica(self):
        """Test detection of 'clasica' variant hint."""
        hints = detect_variant_hints("agrego stock de clasicas")
        assert "clasica" in hints

    def test_apply_variant_hint_when_missing(self):
        """Test that variant hint is applied when missing from product_ref."""
        item = {"product_ref": "pulsera", "quantity": 10}
        variant_hints = {"dorada"}

        result = apply_variant_hint(item, variant_hints)

        # Should append "dorada" to product_ref
        assert "dorada" in result["product_ref"].lower()

    def test_apply_variant_hint_skips_if_already_present(self):
        """Test that variant hint is NOT applied if already present."""
        # Item already has "dorada" variant
        item = {"product_ref": "pulsera dorada", "quantity": 10}
        variant_hints = {"dorada", "negra"}  # Multiple hints available

        result = apply_variant_hint(item, variant_hints)

        # Should NOT add "negra" since "dorada" is already present
        assert result["product_ref"] == "pulsera dorada"
        assert "negra" not in result["product_ref"].lower()

    def test_enforce_variant_alignment_retries_resolution(self, populated_db):
        """Test that variant alignment retries resolution with correct variant."""
        original_item = {"product_ref": "pulsera", "quantity": 5}
        # Suppose this resolved to Clásica (ID 1) initially
        resolved_item = {
            **original_item,
            "product_id": 1,
            "resolved_name": "Pulsera de Granos de Café - Clásica"
        }
        variant_hints = {"dorada"}  # But user said "dorada"

        # enforce_variant_alignment should retry with "dorada"
        result = enforce_variant_alignment(original_item, resolved_item, variant_hints)

        # Should now resolve to Dorada (ID 3)
        assert result["product_id"] == 3
        assert "Dorada" in result["resolved_name"]


# ==============================================================================
# VARIANT RESOLUTION PARAMETRIZED (Comprehensive test)
# ==============================================================================

@pytest.mark.unit
@pytest.mark.parametrize("input_ref,expected_id,expected_keyword", [
    ("doradas", 3, "Dorada"),
    ("negras", 2, "Negra"),
    ("clasicas", 1, "Clásica"),
    ("gold", 3, "Dorada"),
    ("black", 2, "Negra"),
    ("classic", 1, "Clásica"),
])
def test_resolve_variants_parametrized(populated_db, input_ref, expected_id, expected_keyword):
    """Parametrized test for various variant references."""
    item = {"product_ref": input_ref, "quantity": 1}
    result = resolve_product_reference(item)

    assert result["product_id"] == expected_id
    assert expected_keyword in result["resolved_name"]


# ==============================================================================
# DATE RESOLUTION & VALIDATION TESTS (6 tests)
# ==============================================================================

@pytest.mark.unit
class TestDateResolution:
    """Tests for date resolution functions."""

    def test_resolve_date_hoy(self):
        """Test that 'hoy' resolves to today's date."""
        result = resolve_date("hoy")
        expected = datetime.now().date().isoformat()
        assert result == expected

    def test_resolve_date_ayer(self):
        """Test that 'ayer' resolves to yesterday's date."""
        result = resolve_date("ayer")
        expected = (datetime.now().date() - timedelta(days=1)).isoformat()
        assert result == expected

    def test_resolve_date_iso_format(self):
        """Test that ISO date format is returned as-is."""
        iso_date = "2024-01-15"
        result = resolve_date(iso_date)
        assert result == iso_date


@pytest.mark.unit
class TestFieldValidation:
    """Tests for required field validation."""

    def test_validate_register_sale_missing_items(self):
        """Test validation for REGISTER_SALE without items."""
        entities = {}  # No items
        missing = validate_required_fields("REGISTER_SALE", entities)

        assert "items" in missing

    def test_validate_register_product_missing_name(self):
        """Test validation for REGISTER_PRODUCT without name."""
        entities = {"unit_price_cents": 1000}  # Missing name
        missing = validate_required_fields("REGISTER_PRODUCT", entities)

        assert "name" in missing

    def test_validate_add_stock_missing_quantity(self):
        """Test validation for ADD_STOCK without quantity."""
        entities = {"product_id": 1}  # Missing quantity
        missing = validate_required_fields("ADD_STOCK", entities)

        assert "quantity" in missing


# ==============================================================================
# UTILITY FUNCTION TESTS
# ==============================================================================

@pytest.mark.unit
class TestUtilityFunctions:
    """Tests for utility functions in resolver."""

    def test_normalize_text_removes_accents(self):
        """Test that normalize_text removes accents."""
        assert normalize_text("Café") == "cafe"
        assert normalize_text("Pulsera") == "pulsera"
        assert normalize_text("Clásica") == "clasica"

    def test_generate_word_variations_plural_to_singular(self):
        """Test word variations: plural to singular."""
        variations = generate_word_variations("pulseras")
        assert "pulseras" in variations
        assert "pulsera" in variations

    def test_generate_word_variations_singular_to_plural(self):
        """Test word variations: singular to plural."""
        variations = generate_word_variations("pulsera")
        assert "pulsera" in variations
        assert "pulseras" in variations

    def test_translate_product_terms_bidirectional(self):
        """Test that translations work in both directions."""
        # Spanish → English
        variations_es = translate_product_terms("negra")
        assert "black" in " ".join(variations_es)

        # English → Spanish
        variations_en = translate_product_terms("black")
        assert "negra" in " ".join(variations_en)

    def test_generate_sku_from_name_pulsera(self):
        """Test SKU generation from product name (pulsera)."""
        sku = generate_sku_from_name("Pulseras Azules")
        assert sku == "BC-PULS-AZUL"

    def test_generate_sku_from_name_llavero(self):
        """Test SKU generation from product name (llavero)."""
        sku = generate_sku_from_name("Llavero Rojo")
        assert sku == "BC-LLAV-ROJA"

    def test_generate_sku_from_name_fallback(self):
        """Test SKU generation with fallback for unknown type/color."""
        sku = generate_sku_from_name("Unknown Product Name")
        assert sku.startswith("BC-")
        assert "PROD" in sku or "STD" in sku
