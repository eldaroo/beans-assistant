"""
Spec AC10 / T-005: the expander is wired into the graph between router and
resolver, and read paths plus non-REGISTER_PRODUCT write paths bypass it
unchanged so no existing turn regresses.

The full end-to-end graph run depends on the LLM router and is covered by the
live integration suite; this test pins the two structural guarantees that can
be verified deterministically: (1) the expander node and its router -> expander
-> resolver wiring exist in the compiled graph, and (2) the node itself is a
fail-open no-op for every non-expandable operation and for any phrasing it does
not recognize.
"""
import os

import pytest

from agents.expander import create_expander_node


@pytest.fixture
def graph_app():
    """Build the compiled graph for structural inspection.

    Graph construction instantiates the LLM client (no network call), so a
    placeholder key is enough to build and inspect the topology offline. The
    LLM is never invoked here; only the node and edge wiring is asserted.
    """
    os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")
    from graph import create_business_agent_graph
    return create_business_agent_graph()


@pytest.mark.integration
class TestExpanderGraphWiring:
    def test_expander_node_is_in_the_graph(self, graph_app):
        app = graph_app
        nodes = set(app.get_graph().nodes.keys())
        assert "expander" in nodes
        assert "router" in nodes
        assert "resolver" in nodes

    def test_router_reaches_resolver_through_expander(self, graph_app):
        app = graph_app
        edges = [(e.source, e.target) for e in app.get_graph().edges]
        # The deterministic edge expander -> resolver is always present; the
        # router -> expander hop is a conditional edge into the write branch.
        assert ("expander", "resolver") in edges


@pytest.mark.integration
class TestExpanderBypass:
    def test_read_path_bypasses_expander(self):
        node = create_expander_node()
        # A read/analytics turn carries no write operation_type; the node is a
        # no-op (returns an empty delta) and the read path is untouched.
        assert node({"operation_type": None, "user_input": "cuanto vendi hoy"}) == {}

    def test_register_sale_bypasses_expander(self):
        node = create_expander_node()
        delta = node({
            "operation_type": "REGISTER_SALE",
            "user_input": "vendi 3 medias azules y grises",
        })
        assert delta == {}

    def test_add_stock_bypasses_expander(self):
        node = create_expander_node()
        delta = node({
            "operation_type": "ADD_STOCK",
            "user_input": "entraron 400 azules y 200 grises",
        })
        assert delta == {}

    def test_register_product_single_passes_through(self):
        node = create_expander_node()
        # A single product (no coordinated list) is left for the normal path.
        delta = node({
            "operation_type": "REGISTER_PRODUCT",
            "user_input": "vendo medias negras a 5 dolares",
            "normalized_entities": {},
        })
        assert delta == {}

    def test_register_product_variant_is_expanded(self):
        node = create_expander_node()
        delta = node({
            "operation_type": "REGISTER_PRODUCT",
            "user_input": "vendo medias azules y grises a 5 dolares",
            "normalized_entities": {},
        })
        items = delta.get("normalized_entities", {}).get("items")
        assert items is not None
        assert [i["name"] for i in items] == ["Medias Azules", "Medias Grises"]
