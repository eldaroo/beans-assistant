"""
Spec T-003 / T-004 / AC1 / AC2 / AC6: the deterministic attribute expander
turns a base noun plus a coordinated color or size list with a shared price
into a concrete set of items, and stays out of the way otherwise.

Pure module test (agents.expander has no DB or LLM dependency).
"""
import pytest
from agents.expander import expand_items


@pytest.mark.unit
class TestColorExpansion:
    def test_two_colors_share_price(self):
        items = expand_items("vendo medias azules y grises a 5 dolares")
        assert items is not None
        assert [i["name"] for i in items] == ["Medias Azules", "Medias Grises"]
        assert all(i["unit_price_cents"] == 500 for i in items)

    def test_dollar_sign_price_form(self):
        items = expand_items("pulseras rojas y verdes $8")
        assert items is not None
        assert len(items) == 2
        assert all(i["unit_price_cents"] == 800 for i in items)


@pytest.mark.unit
class TestSizeExpansion:
    def test_three_sizes_share_price_and_retain_size(self):
        items = expand_items("medias multicolor talle s, m y l a 10 dolares")
        assert items is not None
        assert [i["name"] for i in items] == [
            "Medias Multicolor Talle S",
            "Medias Multicolor Talle M",
            "Medias Multicolor Talle L",
        ]
        assert all(i["unit_price_cents"] == 1000 for i in items)


@pytest.mark.unit
class TestGateAndPassthrough:
    def test_bare_numbers_are_not_expanded(self):
        # "medias 22, soquetes 15" is genuinely ambiguous (price or stock) and
        # must pass through untouched so the router AMBIGUOUS path still fires.
        assert expand_items("medias 22, soquetes 15") is None

    def test_single_product_passes_through(self):
        assert expand_items("vendo medias negras a 5 dolares") is None

    def test_empty_input(self):
        assert expand_items("") is None

    def test_two_nouns_one_color_each_not_expanded(self):
        # A second noun inside the run means it is not one base with a list.
        assert expand_items("medias azules y soquetes grises a 5 dolares") is None
