"""
Integration test for the decomposer wired into the full LangGraph workflow.

Strategy:
- Build the workflow manually (mirroring `create_business_agent_graph`) but
  inject mocked LLMs so no provider is hit.
- The router LLM mock returns a REGISTER_SALE classification with a
  product_ref matching the sub-input.
- The resolver LLM is unused because we shortcut at the resolver level by
  pre-populating the database via a small in-memory stand-in. We instead
  bypass the database by patching `agents.resolver.fetch_one` /
  `fetch_all` to return one matching product per call.
- The decomposer LLM splits the multi-intent input into three sub-inputs.
- Asserts: final_answer is a single multi-line bubble with three product
  lines and `metadata.sub_input_results` length 3.

This is a high-level smoke that proves the topology re-enters the router
once per sub-input, accumulates results, and emits one aggregated bubble.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from agents import (
    AgentState,
    create_router_agent,
    create_read_agent,
    create_write_agent,
    create_resolver_agent,
    create_decomposer_agent,
    route_to_next_node,
    route_after_write,
    route_after_resolver,
)
from graph import (
    create_final_answer_node,
    create_sub_input_advancer_node,
    route_after_final_answer,
)


def _decomposer_llm():
    """Returns a Runnable that splits 'vendo X, Y y Z' into three sub-inputs."""
    payload = json.dumps({
        "sub_inputs": [
            "vendo medias",
            "vendo pantaletas",
            "vendo soquetes",
        ]
    })

    def _invoke(_prompt_value):
        return AIMessage(content=payload)

    return RunnableLambda(_invoke)


def _router_llm():
    """Returns a Runnable that classifies any input as REGISTER_SALE with the
    product_ref derived from the input string."""

    def _invoke(prompt_value):
        # Pull the user input out of the prompt value.
        text = ""
        if hasattr(prompt_value, "to_messages"):
            messages = prompt_value.to_messages()
            for m in messages:
                if getattr(m, "type", None) == "human":
                    text = m.content
                    break
        product_ref = "producto"
        # Crude extraction: drop the verb if present and treat the rest as
        # the product reference.
        cleaned = text.replace("Mensaje actual:", "").strip()
        for verb in ("vendo ", "vendi ", "compre ", "registro "):
            if cleaned.startswith(verb):
                product_ref = cleaned[len(verb):].strip()
                break
        else:
            product_ref = cleaned

        result = {
            "intent": "WRITE_OPERATION",
            "operation_type": "REGISTER_SALE",
            "confidence": 0.95,
            "missing_fields": [],
            "normalized_entities": {
                "items": [{"product_ref": product_ref, "quantity": 1}]
            },
            "reasoning": "mock router",
            "clarifier": None,
        }
        return AIMessage(content=json.dumps(result))

    return RunnableLambda(_invoke)


@pytest.mark.integration
def test_multi_intent_emits_aggregated_bubble(monkeypatch):
    """vendo medias, pantaletas y soquetes -> 3 sub-inputs -> 3 sales -> one bubble."""

    # --- Patch the database layer so the resolver finds each product. ---
    products = {
        "medias": {"id": 1, "sku": "BC-MED", "name": "Medias"},
        "pantaletas": {"id": 2, "sku": "BC-PAN", "name": "Pantaletas"},
        "soquetes": {"id": 3, "sku": "BC-SOQ", "name": "Soquetes"},
    }

    def fake_fetch_one(query: str, params: tuple = ()):  # type: ignore[no-untyped-def]
        # Resolver issues two flavors of query: exact SKU match and
        # name-LIKE match. Return the matching product if any params hit.
        if not params:
            return None
        param = params[0] if params else ""
        if isinstance(param, str):
            lowered = param.lower().strip("%")
            for key, prod in products.items():
                if key in lowered or prod["sku"].lower() == lowered:
                    return dict(prod)
        return None

    def fake_fetch_all(query: str, params: tuple = ()):  # type: ignore[no-untyped-def]
        return [dict(p) for p in products.values()]

    monkeypatch.setattr("agents.resolver.fetch_one", fake_fetch_one)
    monkeypatch.setattr("agents.resolver.fetch_all", fake_fetch_all)

    # --- Patch the write_agent register_sale + price-block fetch_one. ---
    sale_counter = {"n": 0}

    def fake_register_sale(sale_data: Dict[str, Any]) -> Dict[str, Any]:
        sale_counter["n"] += 1
        return {
            "sale_id": sale_counter["n"],
            "total_usd": 35.0,
            "revenue_usd": 35.0 * sale_counter["n"],
            "profit_usd": 20.0 * sale_counter["n"],
        }

    monkeypatch.setattr("agents.write_agent.register_sale", fake_register_sale)

    # The write_agent's null-price guard hits fetch_one against products
    # to check for unit_price_cents. Our mock products have no price; the
    # guard would block the sale. Force it to return a row with a price
    # set so the sale proceeds.
    def fake_write_fetch_one(query: str, params: tuple = ()):  # type: ignore[no-untyped-def]
        # Returns a non-null price so the sale isn't blocked by the
        # null-price guard.
        return {"name": "X", "unit_price_cents": 3500}

    monkeypatch.setattr("agents.write_agent.fetch_one", fake_write_fetch_one)

    # --- Build the graph manually with mocked LLMs. ---
    decomposer = create_decomposer_agent(_decomposer_llm())
    router = create_router_agent(_router_llm())
    write_agent = create_write_agent()
    resolver = create_resolver_agent(_router_llm())
    read_agent = create_read_agent(_router_llm())

    workflow = StateGraph(AgentState)
    workflow.add_node("decomposer", decomposer)
    workflow.add_node("router", router)
    workflow.add_node("read_agent", read_agent)
    workflow.add_node("write_agent", write_agent)
    workflow.add_node("resolver", resolver)
    workflow.add_node("final_answer", create_final_answer_node())
    workflow.add_node("sub_input_advancer", create_sub_input_advancer_node())

    workflow.set_entry_point("decomposer")
    workflow.add_edge("decomposer", "router")
    workflow.add_conditional_edges("router", route_to_next_node, {
        "read_agent": "read_agent",
        "resolver": "resolver",
        "final_answer": "final_answer",
    })
    workflow.add_conditional_edges("resolver", route_after_resolver, {
        "write_agent": "write_agent",
        "final_answer": "final_answer",
    })
    workflow.add_conditional_edges("write_agent", route_after_write, {
        "read_agent": "read_agent",
        "final_answer": "final_answer",
    })
    workflow.add_edge("read_agent", "final_answer")
    workflow.add_conditional_edges("final_answer", route_after_final_answer, {
        "sub_input_advancer": "sub_input_advancer",
        "end": END,
    })
    workflow.add_edge("sub_input_advancer", "router")
    graph = workflow.compile()

    # --- Run. ---
    initial_state: AgentState = {  # type: ignore[typeddict-item]
        "messages": [],
        "user_input": "vendo medias, pantaletas y soquetes",
        "phone": "+5491100000000",
        "sender": "+5491100000000",
        "intent": None,
        "operation_type": None,
        "confidence": None,
        "missing_fields": [],
        "normalized_entities": {},
        "sql_result": None,
        "operation_result": None,
        "final_answer": None,
        "error": None,
        "next_action": None,
        "metadata": {},
    }

    config = RunnableConfig(recursion_limit=50)
    result = graph.invoke(initial_state, config)

    # --- Assert: aggregated bubble with three product lines. ---
    metadata = result.get("metadata") or {}
    sub_input_results = metadata.get("sub_input_results") or []

    assert len(sub_input_results) == 3, sub_input_results
    successes = [r for r in sub_input_results if r["success"]]
    assert len(successes) == 3, sub_input_results

    final = result["final_answer"]
    assert final, "final_answer must be set"
    # Single multi-line bubble: starts with the success header and
    # contains all three products.
    assert "Listo. Cargue:" in final
    # Each sub-input's product appears at least once in the bubble.
    for product in ("Medias", "Pantaletas", "Soquetes"):
        assert product in final, f"missing {product} in bubble: {final}"
    # No N separate bubbles: the assistant returns a single string.
    assert isinstance(final, str)

    # The decomposer's split produced exactly 3 entries on the queue.
    assert metadata.get("sub_input_queue") == [
        "vendo medias",
        "vendo pantaletas",
        "vendo soquetes",
    ]
    # And ran each one (cursor is at the last index).
    assert metadata.get("sub_input_cursor") == 2
