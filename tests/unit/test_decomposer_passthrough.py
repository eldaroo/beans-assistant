"""
Verify that the decomposer node skips the LLM entirely on single-intent inputs.

Per ADR Decision 2, single-intent (gate returns False) means zero LLM call,
zero added latency. We assert the LLM mock is never invoked AND the state
delta seeds `metadata.sub_input_queue = [user_input]` and rewrites
`state["user_input"]` to the same value.
"""
import json

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from agents.decomposer import create_decomposer_agent


def _spy_llm():
    """Real Runnable that records every invocation. The test asserts it
    stays at zero invocations on the single-intent path."""
    invocations = []

    def _invoke(prompt_value):
        invocations.append(prompt_value)
        return AIMessage(content=json.dumps({"sub_inputs": ["FORBIDDEN"]}))

    runnable = RunnableLambda(_invoke)
    runnable._invocations = invocations  # type: ignore[attr-defined]
    return runnable


@pytest.mark.unit
class TestDecomposerPassThrough:
    def test_single_intent_does_not_call_llm(self):
        llm = _spy_llm()
        decompose = create_decomposer_agent(llm)

        state = {
            "user_input": "vendi 5 medias",
            "metadata": {"phone": "+5491100000000"},
            "messages": [],
        }
        decompose(state)

        # Zero LLM dispatches when the gate says no.
        assert llm._invocations == []

    def test_passthrough_seeds_queue(self):
        llm = _spy_llm()
        decompose = create_decomposer_agent(llm)

        state = {
            "user_input": "cuanto stock tengo",
            "metadata": {"phone": "+5491100000000", "owner_name": "Dario"},
            "messages": [],
        }

        delta = decompose(state)

        metadata = delta["metadata"]
        assert metadata["sub_input_queue"] == ["cuanto stock tengo"]
        assert metadata["sub_input_cursor"] == 0
        assert metadata["sub_input_results"] == []
        # Pre-existing metadata keys must survive.
        assert metadata["phone"] == "+5491100000000"
        assert metadata["owner_name"] == "Dario"
        # user_input is unchanged for single-intent.
        assert delta["user_input"] == "cuanto stock tengo"
        # And the LLM was not touched.
        assert llm._invocations == []

    def test_passthrough_empty_input(self):
        llm = _spy_llm()
        decompose = create_decomposer_agent(llm)

        state = {"user_input": "", "metadata": {}, "messages": []}
        delta = decompose(state)

        assert delta["metadata"]["sub_input_queue"] == [""]
        assert llm._invocations == []
