"""
Spec T-007 / D-004: compose_base_sku retains discriminating tokens (colors and
sizes, including single-letter sizes) so variants of one base do not collide;
dedup_skus makes a list unique against its in-flight siblings.

Pure module test (agents.sku has no DB or LLM dependency).
"""
import pytest
from agents.sku import compose_base_sku, dedup_skus


@pytest.mark.unit
class TestComposeBaseSku:
    def test_size_token_retained_and_distinct(self):
        s = compose_base_sku("Medias Multicolor Talle S")
        m = compose_base_sku("Medias Multicolor Talle M")
        l = compose_base_sku("Medias Multicolor Talle L")
        assert s != m != l and s != l, (s, m, l)
        # The size is the discriminator that must survive.
        assert s.endswith("-S") and m.endswith("-M") and l.endswith("-L")

    def test_color_variants_distinct(self):
        azul = compose_base_sku("Medias Azules")
        gris = compose_base_sku("Medias Grises")
        assert azul != gris
        assert "AZUL" in azul and "GRIS" in gris

    def test_type_token_preserved(self):
        assert compose_base_sku("Pulseras Negras").startswith("BC-PULS-")
        assert compose_base_sku("Medias Azules").startswith("BC-PROD-")

    def test_no_descriptor_falls_back_to_std(self):
        assert compose_base_sku("Pulseras").endswith("-STD")


@pytest.mark.unit
class TestDedupSkus:
    def test_collisions_get_suffixes(self):
        assert dedup_skus(["A", "A", "A"]) == ["A", "A-2", "A-3"]

    def test_distinct_unchanged(self):
        assert dedup_skus(["A", "B", "C"]) == ["A", "B", "C"]

    def test_order_preserved(self):
        assert dedup_skus(["X", "Y", "X"]) == ["X", "Y", "X-2"]
