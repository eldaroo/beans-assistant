"""
Tests for the decomposer LLM split path.

When `should_decompose` returns True, the decomposer invokes a chain
`prompt | llm | parser`. We use a fake LLM Runnable whose `.invoke()`
returns an AIMessage carrying the JSON we want — that exercises the real
LangChain prompt-format and JsonOutputParser pipeline without hitting any
provider.
"""
import json

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from agents.decomposer import (
    MAX_SUB_INPUTS,
    create_decomposer_agent,
)


def _fake_llm(sub_inputs):
    """Build a Runnable that always returns an AIMessage with the given
    sub_inputs as JSON content. Compatible with `prompt | llm | parser`."""
    payload = json.dumps({"sub_inputs": list(sub_inputs)}, ensure_ascii=False)

    invocations = []

    def _invoke(prompt_value):
        invocations.append(prompt_value)
        return AIMessage(content=payload)

    runnable = RunnableLambda(_invoke)
    runnable._invocations = invocations  # type: ignore[attr-defined]
    return runnable


def _broken_llm():
    """Runnable that raises on invoke — exercises the fallback path."""
    def _invoke(prompt_value):
        raise RuntimeError("LLM down")
    return RunnableLambda(_invoke)


@pytest.mark.unit
class TestDecomposerSplit:
    def test_split_three_sub_inputs(self):
        llm = _fake_llm([
            "vendo medias",
            "vendo pantaletas",
            "vendo soquetes",
        ])
        decompose = create_decomposer_agent(llm)

        state = {
            "user_input": "vendo medias, pantaletas y soquetes",
            "metadata": {"phone": "+5491100000000"},
            "messages": [],
        }
        delta = decompose(state)

        # The chain must have been invoked exactly once.
        assert len(llm._invocations) == 1

        metadata = delta["metadata"]
        assert metadata["sub_input_queue"] == [
            "vendo medias",
            "vendo pantaletas",
            "vendo soquetes",
        ]
        assert metadata["sub_input_cursor"] == 0
        assert metadata["sub_input_results"] == []
        # Router runs against the first sub-input, not the original message.
        assert delta["user_input"] == "vendo medias"

    def test_split_strips_whitespace_and_drops_empties(self):
        llm = _fake_llm(["  vendo medias  ", "", "vendo soquetes"])
        decompose = create_decomposer_agent(llm)

        state = {
            "user_input": "vendo medias, pantaletas y soquetes",
            "metadata": {},
            "messages": [],
        }
        delta = decompose(state)

        assert delta["metadata"]["sub_input_queue"] == [
            "vendo medias",
            "vendo soquetes",
        ]

    def test_llm_failure_falls_back_to_single_intent(self):
        decompose = create_decomposer_agent(_broken_llm())

        state = {
            "user_input": "vendo medias, pantaletas y soquetes",
            "metadata": {},
            "messages": [],
        }
        delta = decompose(state)

        # Degraded gracefully to single-intent.
        assert delta["metadata"]["sub_input_queue"] == [
            "vendo medias, pantaletas y soquetes"
        ]
        assert delta["user_input"] == "vendo medias, pantaletas y soquetes"

    def test_truncates_at_max_sub_inputs(self):
        emitted = [f"accion {i}" for i in range(MAX_SUB_INPUTS + 3)]
        llm = _fake_llm(emitted)
        decompose = create_decomposer_agent(llm)

        state = {
            "user_input": (
                "vendo a, vendo b, vendo c, vendo d, vendo e, vendo f, "
                "vendo g, vendo h, vendo i, vendo j, vendo k, vendo l y vendo m"
            ),
            "metadata": {},
            "messages": [],
        }
        delta = decompose(state)

        metadata = delta["metadata"]
        assert len(metadata["sub_input_queue"]) == MAX_SUB_INPUTS
        # The truncation tail surfaces in sub_input_results so the final
        # summary can mention the dropped items.
        assert len(metadata["sub_input_results"]) == 3
        assert all(
            entry["success"] is False
            for entry in metadata["sub_input_results"]
        )
