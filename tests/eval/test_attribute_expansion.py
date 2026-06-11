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
