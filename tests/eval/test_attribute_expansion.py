"""
Spec T-002 / T-010 / AC3: the screenshot golden.

The real onboarding input that failed twice now expands to five concrete
products at the right prices, each with a distinct SKU. This asserts the
deterministic layer (expander grammar plus SKU composition plus in-batch
dedup) end to end. The full graph path (router classification, resolver, write
agent, DB commit) is covered by the integration suite; this golden pins the
interpretation contract that the screenshot input produces five priced
products with unique SKUs.
"""
import pytest
from agents.expander import expand_items
from agents.sku import compose_base_sku, dedup_skus


# The decomposer splits the screenshot input on the top-level comma into two
# product phrases. This golden drives each phrase through the expander.
SCREENSHOT_SUBINPUTS = [
    "vendo medias azules y grises a 5 dolares",
    "y medias multicolor talle s, m y l a 10 dolares",
]


@pytest.mark.eval
def test_screenshot_input():
    items = []
    for phrase in SCREENSHOT_SUBINPUTS:
        expanded = expand_items(phrase)
        assert expanded is not None, f"phrase did not expand: {phrase}"
        items.extend(expanded)

    # Five products total.
    assert len(items) == 5

    names = [i["name"] for i in items]
    assert names == [
        "Medias Azules",
        "Medias Grises",
        "Medias Multicolor Talle S",
        "Medias Multicolor Talle M",
        "Medias Multicolor Talle L",
    ]

    # Shared price distributed correctly across each phrase.
    prices = [i["unit_price_cents"] for i in items]
    assert prices == [500, 500, 1000, 1000, 1000]

    # Every product gets a distinct SKU after composition plus in-batch dedup.
    skus = dedup_skus([compose_base_sku(n) for n in names])
    assert len(set(skus)) == 5, f"SKUs collide: {skus}"


# Spec T-018 / AC: sibling-phrasing golden pack. The screenshot is one shape of
# the same grammar; these pin the neighboring phrasings an owner actually types
# so a future prompt or grammar edit cannot silently regress them.
SIBLING_GOLDENS = [
    # (phrase, expected_names, expected_price_cents)
    (
        "pulseras rojas, verdes y azules a 3 dolares",
        ["Pulseras Rojas", "Pulseras Verdes", "Pulseras Azules"],
        300,
    ),
    (
        "gorras negras y blancas $12",
        ["Gorras Negras", "Gorras Blancas"],
        1200,
    ),
    (
        "remeras talle s y m a 8 dolares",
        ["Remeras Talle S", "Remeras Talle M"],
        800,
    ),
    (
        "medias azules, grises y negras a 5 dolares",
        ["Medias Azules", "Medias Grises", "Medias Negras"],
        500,
    ),
]


@pytest.mark.eval
@pytest.mark.parametrize("phrase,expected_names,price", SIBLING_GOLDENS)
def test_sibling_phrasings(phrase, expected_names, price):
    items = expand_items(phrase)
    assert items is not None, f"phrase did not expand: {phrase}"
    assert [i["name"] for i in items] == expected_names
    assert all(i["unit_price_cents"] == price for i in items)
    # Distinct SKUs after composition plus in-batch dedup.
    skus = dedup_skus([compose_base_sku(n) for n in expected_names])
    assert len(set(skus)) == len(expected_names), f"SKUs collide: {skus}"


@pytest.mark.eval
def test_bare_number_sibling_does_not_expand():
    """The bare-number ambiguity case stays unexpanded (spec AC6)."""
    assert expand_items("medias 22, soquetes 15") is None
