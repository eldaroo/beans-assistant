"""
Spec T-017: the router prompt carries explicit variant-phrasing examples so a
base noun plus a color or size list with a shared price classifies as
REGISTER_PRODUCT, while a bare-number list ("medias 22, soquetes 15") stays
AMBIGUOUS.

This is a contract test, not a runtime path change (per plan.md): it grates the
prompt source for the guidance rather than calling the LLM, so it is
deterministic and cost-free. The runtime classification is exercised by the
router routing suite and, end to end, by the integration suite.
"""
import re
from pathlib import Path

import pytest

ROUTER_SRC = (Path(__file__).resolve().parents[2] / "agents" / "router.py").read_text(
    encoding="utf-8"
)


@pytest.mark.unit
class TestRouterVariantPromptExamples:
    def test_variant_examples_present(self):
        # The two screenshot-shaped variant phrasings appear as REGISTER_PRODUCT
        # examples in the prompt.
        assert "medias azules y grises a 5 dolares" in ROUTER_SRC
        assert "talle s, m y l" in ROUTER_SRC.lower()

    def test_variant_examples_classify_as_register_product(self):
        # The variant guidance block names REGISTER_PRODUCT and tells the model
        # NOT to emit AMBIGUOUS for the shared-price variant case.
        assert "VARIANT phrasing is REGISTER_PRODUCT" in ROUTER_SRC

    def test_bare_number_still_ambiguous(self):
        # The bare-number ambiguity rule is preserved next to the variant rule.
        assert "medias 22, soquetes 15" in ROUTER_SRC
        # And it routes to AMBIGUOUS with the price-or-stock clarifier.
        assert re.search(r"precios.*cantidades|cantidades.*precios", ROUTER_SRC, re.IGNORECASE | re.DOTALL)
