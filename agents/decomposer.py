"""
Decomposer Agent - Splits multi-intent user messages into sub-inputs before routing.

Responsibilities:
- Inspect the raw user_input.
- Run a pre-LLM regex gate (LIST_SEPARATOR or MULTI_VERB) to decide if the
  message likely combines multiple business actions.
- For single-intent inputs, pass through as `[user_input]` with zero LLM call.
- For multi-intent inputs, invoke a cheap LLM (Haiku-class) to split the
  message into self-contained sub-messages, one per action.
- Seed sub_input_queue, sub_input_cursor, sub_input_results in metadata so
  the graph can re-enter the router per sub-input.
- NO intent classification. NO execution. NO database writes.

This module contracts with the ADR
`_brain/output/architecture/timonel-decomposer-adr.md` (PR-B).
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .state import AgentState


# Hard cap on sub-inputs per turn. The graph runs with recursion_limit=50;
# each sub-input consumes ~3-4 nodes, so 10 sits comfortably under the limit.
MAX_SUB_INPUTS = 10


# Regex spec per ADR Decision 2.
# LIST_SEPARATOR matches a list of 3+ items separated by `,`, ` y `, or newline.
LIST_SEPARATOR = re.compile(
    r"(?:[^,\n]+(?:,|\s+y\s+|\n)){2,}[^,\n]+",
    flags=re.IGNORECASE,
)

# MULTI_VERB triggers when 2+ distinct action verbs appear in the input.
ACTION_VERBS = re.compile(
    r"\b(vendo|vendi|vendí|registro|registrame|agrego|gast[eé]|"
    r"compr[eé]|cancela|anula|cargo|carga|carg[aá]me)\b",
    flags=re.IGNORECASE,
)


def should_decompose(user_input: str) -> bool:
    """Pre-LLM gate. Returns True if user_input is a multi-intent candidate.

    The gate fires if EITHER:
      1. LIST_SEPARATOR matches (a list of 3+ items separated by `,`, ` y `,
         or newline), OR
      2. ACTION_VERBS finds 2+ distinct verb lemmas in the text.

    Pure function. Zero side effects. Used by the decomposer node to skip
    the LLM call on single-intent inputs.
    """
    if not user_input:
        return False

    if LIST_SEPARATOR.search(user_input):
        return True

    verb_matches = ACTION_VERBS.findall(user_input)
    if len(set(m.lower() for m in verb_matches)) >= 2:
        return True

    return False


class DecomposerOutput(BaseModel):
    """Structured output for the decomposer LLM call."""

    sub_inputs: List[str] = Field(
        description=(
            "Lista de sub-mensajes, uno por accion. Si el input es "
            "single-intent, devolver [<input>] sin cambiarlo."
        )
    )


DECOMPOSER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Sos un decomposer. Recibis un mensaje del usuario que combina varias acciones de negocio.

Tu trabajo es partirlo en sub-mensajes, uno por accion. Cada sub-mensaje debe ser autocontenido: incluir verbo, objeto, y modificadores (cantidades, precios, fechas, descripciones) que correspondan a esa accion.

REGLAS:
- NO clasifiques intent. NO digas "esto es REGISTER_SALE".
- NO ejecutes nada.
- NO inventes informacion que no este en el input.
- Si el input ya es single-intent, devolve `{{"sub_inputs": ["<input original>"]}}` sin cambiarlo.
- Si el input combina varias acciones, devolve un sub_input por accion, en orden de aparicion.
- Cada sub_input debe leerse como un mensaje independiente que el router pueda clasificar por si solo.

EJEMPLOS:

Input: "vendo medias, pantaletas y soquetes"
Output: {{"sub_inputs": ["vendo medias", "vendo pantaletas", "vendo soquetes"]}}

Input: "vendi 5 medias y compre 3 peras"
Output: {{"sub_inputs": ["vendi 5 medias", "compre 3 peras"]}}

Input: "vendi 5 pulseras negras"
Output: {{"sub_inputs": ["vendi 5 pulseras negras"]}}

Input: "registre gasto de envios y vendo soquetes"
Output: {{"sub_inputs": ["registre gasto de envios", "vendo soquetes"]}}

Input: "vendo medias 15, pantaletas 20"
Output: {{"sub_inputs": ["vendo medias 15", "vendo pantaletas 20"]}}

Output: JSON valido con la forma `{{"sub_inputs": [str, ...]}}`."""),
    ("user", "{input}"),
])


def _seed_metadata(
    state: AgentState,
    sub_inputs: List[str],
) -> Dict[str, Any]:
    """Compose the metadata delta that seeds the sub-input loop."""
    base_metadata = state.get("metadata") or {}
    new_metadata = {
        **base_metadata,
        "sub_input_queue": list(sub_inputs),
        "sub_input_cursor": 0,
        "sub_input_results": [],
    }
    return new_metadata


def create_decomposer_agent(llm) -> Callable[[AgentState], Dict[str, Any]]:
    """Decomposer factory.

    Returns a node function that, given AgentState, returns a state delta
    with `metadata.sub_input_queue: list[str]` populated and
    `state["user_input"]` rewritten to the first sub-input so the router
    runs against it directly.
    """
    parser = JsonOutputParser(pydantic_object=DecomposerOutput)
    chain = DECOMPOSER_PROMPT | llm | parser

    def decompose(state: AgentState) -> Dict[str, Any]:
        user_input = state.get("user_input") or ""

        # Heuristic gate: pass-through with zero LLM call.
        if not should_decompose(user_input):
            metadata = _seed_metadata(state, [user_input])
            return {
                "metadata": metadata,
                "user_input": user_input,
                "messages": [{
                    "role": "assistant",
                    "content": "[Decomposer] passthrough (single-intent)",
                }],
            }

        # Gate dispatched: invoke LLM to split.
        try:
            result = chain.invoke({"input": user_input})

            # JsonOutputParser returns a dict, not a model instance.
            if isinstance(result, dict):
                sub_inputs = result.get("sub_inputs") or []
            else:
                sub_inputs = getattr(result, "sub_inputs", []) or []

            # Sanitize: drop empties, strip whitespace.
            sub_inputs = [s.strip() for s in sub_inputs if s and s.strip()]

            if not sub_inputs:
                # LLM returned nothing usable. Degrade to single-intent.
                sub_inputs = [user_input]

            # Hard cap. Truncate to MAX_SUB_INPUTS and surface the truncation
            # via a flagged-skip entry in sub_input_results so the final
            # summary can mention it.
            truncated_tail: List[Dict[str, Any]] = []
            if len(sub_inputs) > MAX_SUB_INPUTS:
                dropped = sub_inputs[MAX_SUB_INPUTS:]
                sub_inputs = sub_inputs[:MAX_SUB_INPUTS]
                for ignored in dropped:
                    truncated_tail.append({
                        "sub_input": ignored,
                        "success": False,
                        "summary_or_error": (
                            "Te ignore items por encima del limite de "
                            f"{MAX_SUB_INPUTS} por turno. Mandalos en otro mensaje."
                        ),
                    })

            metadata = _seed_metadata(state, sub_inputs)
            if truncated_tail:
                metadata["sub_input_results"] = truncated_tail

            return {
                "metadata": metadata,
                "user_input": sub_inputs[0],
                "messages": [{
                    "role": "assistant",
                    "content": (
                        f"[Decomposer] split into {len(sub_inputs)} sub-input(s)"
                    ),
                }],
            }

        except Exception as exc:
            # Fall back to single-intent on any LLM/parse failure. This
            # never breaks the turn, the router just sees the raw input.
            metadata = _seed_metadata(state, [user_input])
            return {
                "metadata": metadata,
                "user_input": user_input,
                "messages": [{
                    "role": "assistant",
                    "content": (
                        f"[Decomposer] fallback to single-intent: {exc}"
                    ),
                }],
            }

    return decompose


# Turn-scoped state fields that must be reset between sub-inputs. Anything
# not listed here is preserved across the loop (messages, metadata, phone,
# sender, user_input override). Keep this list in sync with the AgentState
# fields the router/resolver/write_agent fill in per turn.
TURN_SCOPED_FIELDS = (
    "intent",
    "operation_type",
    "confidence",
    "missing_fields",
    "normalized_entities",
    "sql_result",
    "operation_result",
    "error",
    "next_action",
    "final_answer",
)


def _advance_sub_input(state: AgentState) -> Dict[str, Any]:
    """State delta that advances the sub-input cursor.

    - Increments `metadata.sub_input_cursor`.
    - Copies the next sub_input from queue to `state["user_input"]`.
    - Resets all turn-scoped fields (intent, operation_type, ...,
      final_answer) so the router classifies fresh.
    - Preserves messages and the rest of metadata.
    """
    metadata = state.get("metadata") or {}
    queue: List[str] = list(metadata.get("sub_input_queue") or [])
    cursor: int = int(metadata.get("sub_input_cursor") or 0)

    next_cursor = cursor + 1
    if next_cursor >= len(queue):
        # No more sub-inputs. Caller should not have routed here, but be
        # defensive: produce a no-op delta.
        return {}

    next_user_input = queue[next_cursor]
    new_metadata = {
        **metadata,
        "sub_input_cursor": next_cursor,
    }

    delta: Dict[str, Any] = {
        "metadata": new_metadata,
        "user_input": next_user_input,
    }
    # Clear turn-scoped fields so the next sub-input starts fresh.
    for field in TURN_SCOPED_FIELDS:
        if field == "missing_fields":
            delta[field] = []
        elif field == "normalized_entities":
            delta[field] = {}
        else:
            delta[field] = None

    delta["messages"] = [{
        "role": "assistant",
        "content": (
            f"[Decomposer] advancing to sub-input "
            f"{next_cursor + 1}/{len(queue)}: {next_user_input}"
        ),
    }]
    return delta


def flush_sub_input_result(
    state: AgentState,
    success: bool,
) -> Dict[str, Any]:
    """State delta: append the current sub-input's result to sub_input_results.

    Reads the active sub_input via metadata.sub_input_queue[cursor],
    captures the human-readable summary (final_answer on success, error on
    failure, falling back to a generic notice), and appends a record. Used
    by the conditional edge after final_answer / write_agent.
    """
    metadata = state.get("metadata") or {}
    queue: List[str] = list(metadata.get("sub_input_queue") or [])
    cursor: int = int(metadata.get("sub_input_cursor") or 0)

    if not queue or cursor >= len(queue):
        return {}

    active_sub_input = queue[cursor]

    if success:
        summary = (
            state.get("final_answer")
            or state.get("sql_result")
            or "OK"
        )
    else:
        summary = (
            state.get("error")
            or state.get("final_answer")
            or "fallo sin detalle"
        )

    results: List[Dict[str, Any]] = list(metadata.get("sub_input_results") or [])
    results.append({
        "sub_input": active_sub_input,
        "success": bool(success),
        "summary_or_error": summary,
    })

    new_metadata = {
        **metadata,
        "sub_input_results": results,
    }
    return {"metadata": new_metadata}
