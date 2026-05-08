"""
LangGraph Multi-Agent Orchestration for Beans&Co Business Agent.

This module defines the complete workflow graph that routes user requests
through specialized agents based on intent classification.

Flow (per turn):
    decomposer
        -> router
            -> read_agent | (resolver -> write_agent -> read_agent?)
        -> final_answer
            -> sub_input_advancer? -> router (next sub-input)
            -> END (last sub-input, optionally with aggregated summary)
"""
import re
from typing import Dict, Any, List
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
    flush_sub_input_result,
    _advance_sub_input,
)
from llm import get_llm, get_llm_cheap


def create_business_agent_graph(db_path: str = "sqlite:///beansco.db"):
    """
    Create the complete multi-agent business workflow graph.

    Args:
        db_path: Database connection string

    Returns:
        Compiled LangGraph workflow
    """
    # Initialize LLMs
    llm = get_llm()  # Main LLM for router and read agent
    llm_cheap = get_llm_cheap()  # Cheap LLM for resolver and decomposer

    # Create specialized agents
    decomposer = create_decomposer_agent(llm_cheap)
    router = create_router_agent(llm)
    read_agent = create_read_agent(llm)  # Custom read agent (no db_path needed)
    write_agent = create_write_agent()
    resolver = create_resolver_agent(llm_cheap)  # Use cheap LLM for product disambiguation

    # Define the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("decomposer", decomposer)
    workflow.add_node("router", router)
    workflow.add_node("read_agent", read_agent)
    workflow.add_node("write_agent", write_agent)
    workflow.add_node("resolver", resolver)
    workflow.add_node("final_answer", create_final_answer_node())
    workflow.add_node("sub_input_advancer", create_sub_input_advancer_node())

    # Decomposer is the new entry point (it seeds the sub-input queue and
    # may rewrite user_input to the first sub-input, then yields to router).
    workflow.set_entry_point("decomposer")
    workflow.add_edge("decomposer", "router")

    # Conditional edges from router
    workflow.add_conditional_edges(
        "router",
        route_to_next_node,
        {
            "read_agent": "read_agent",
            "resolver": "resolver",
            "final_answer": "final_answer",
        }
    )

    # Conditional edges from resolver
    workflow.add_conditional_edges(
        "resolver",
        route_after_resolver,
        {
            "write_agent": "write_agent",
            "final_answer": "final_answer",
        }
    )

    # Conditional edges from write_agent
    workflow.add_conditional_edges(
        "write_agent",
        route_after_write,
        {
            "read_agent": "read_agent",
            "final_answer": "final_answer",
        }
    )

    # Read agent always goes to final answer
    workflow.add_edge("read_agent", "final_answer")

    # Final answer either advances to the next sub-input or ends the turn.
    workflow.add_conditional_edges(
        "final_answer",
        route_after_final_answer,
        {
            "sub_input_advancer": "sub_input_advancer",
            "end": END,
        }
    )

    # Advancer re-enters the router for the next sub-input.
    workflow.add_edge("sub_input_advancer", "router")

    # Compile the graph
    return workflow.compile()


def _has_more_sub_inputs(state: AgentState) -> bool:
    """True iff the sub-input queue has unprocessed entries left."""
    metadata = state.get("metadata") or {}
    queue = metadata.get("sub_input_queue") or []
    cursor = int(metadata.get("sub_input_cursor") or 0)
    return cursor < len(queue) - 1


def _pick_summary_detail(summary: str) -> str:
    """Pull a meaningful one-liner out of a per-sub-input summary.

    The write_agent format is roughly:
        *Venta registrada!*

        - 1 Medias
        - Total: *$35.00*
        ...

    We want the first non-empty line that is NOT the header (no leading
    bullet `-` in the header). Fall back to the entire first line if
    nothing detail-shaped is present.
    """
    if not summary:
        return ""
    lines = [ln.strip() for ln in summary.splitlines() if ln.strip()]
    if not lines:
        return ""
    # Skip the first line if it's a bold header (decorated with *).
    for ln in lines[1:]:
        # Strip leading bullet markers used by the write_agent.
        cleaned = ln.lstrip("-").lstrip("*").lstrip("•").strip()
        if cleaned:
            return cleaned
    # No detail line found, return the first line stripped of decoration.
    return lines[0].lstrip("*").rstrip("*").strip()


def _build_aggregated_summary(results: List[Dict[str, Any]]) -> str:
    """Compose the multi-line summary per ADR Decision 1.

    Layout:
      {exito_block}

      {fallo_block}

    - exito_block: present if any sub-input succeeded.
    - fallo_block: present if any sub-input failed.
    - All-fail message and all-success message are handled inline.
    """
    successes = [r for r in results if r.get("success")]
    failures = [r for r in results if not r.get("success")]

    # All failed: single block.
    if not successes:
        if not failures:
            return "I processed your request, but I'm not sure what to return."
        reasons = "\n".join(
            f"- *{r['sub_input']}*: {r['summary_or_error']}"
            for r in failures
        )
        return f"No pude cargar nada.\n{reasons}"

    # Build the success block: one bullet per succeeded sub-input. Pick the
    # most useful single line from the per-sub-input summary. The
    # write_agent emits a header ("*Venta registrada!*") followed by
    # detail lines ("- 1 Medias"). We prefer the first detail line so the
    # bullet shows what changed; if no detail line is found, fall back to
    # the verbatim sub_input as the user phrased it.
    exito_lines = []
    for r in successes:
        summary = (r.get("summary_or_error") or "").strip()
        detail = _pick_summary_detail(summary) or r.get("sub_input", "")
        exito_lines.append(f"- {detail}")

    exito_block = "Listo. Cargue:\n" + "\n".join(exito_lines)

    if not failures:
        return exito_block

    fallo_lines = []
    for r in failures:
        reason = (r.get("summary_or_error") or "fallo sin detalle").strip()
        # Compact: keep the first line.
        first_line = reason.splitlines()[0] if reason else "fallo sin detalle"
        fallo_lines.append(f"- *{r['sub_input']}*: {first_line}")
    fallo_block = "No pude con:\n" + "\n".join(fallo_lines)

    return f"{exito_block}\n\n{fallo_block}"


def route_after_final_answer(state: AgentState) -> str:
    """Conditional edge from final_answer: advance or end the turn."""
    if _has_more_sub_inputs(state):
        return "sub_input_advancer"
    return "end"


def create_sub_input_advancer_node():
    """Wraps `_advance_sub_input` so it can be registered as a graph node."""

    def advance(state: AgentState) -> Dict[str, Any]:
        return _advance_sub_input(state)

    return advance


def create_final_answer_node():
    """
    Create the final answer node that formats the response to the user.

    Returns:
        Function that formats final answer
    """
    def format_final_answer(state: AgentState) -> Dict[str, Any]:
        """
        Format final answer based on accumulated results.

        Args:
            state: Current agent state

        Returns:
            State with formatted final_answer
        """
        # Compute the per-sub-input final_answer first using the existing logic.
        per_input_delta = _compute_per_sub_input_answer(state)

        # Determine success/failure for the sub-input flush.
        # A sub-input is "successful" if there is no error AND the answer
        # is not a missing-field clarification or ambiguity bounce. We use
        # state's own signals: error => fail; missing_fields => fail
        # (counts as user-input-needed); intent in AMBIGUOUS / DECLINE /
        # PROPOSE_PRODUCT_CREATION => fail-shaped (the operation did not
        # commit). Otherwise success.
        intent = state.get("intent")
        had_error = bool(state.get("error"))
        had_missing = bool(state.get("missing_fields"))
        soft_fail_intents = {
            "AMBIGUOUS",
            "DECLINE_PRODUCT_CREATION",
            "PROPOSE_PRODUCT_CREATION",
        }
        success = (
            not had_error
            and not had_missing
            and intent not in soft_fail_intents
        )

        # Merge state with per-input delta so flush sees the active
        # final_answer / error.
        state_with_answer = {**state, **per_input_delta}
        flush_delta = flush_sub_input_result(state_with_answer, success)

        # Merge flush metadata back.
        final_delta: Dict[str, Any] = dict(per_input_delta)
        if "metadata" in flush_delta:
            final_delta["metadata"] = flush_delta["metadata"]

        # If this is the last sub-input and we accumulated >1 result,
        # replace the partial final_answer with the aggregated summary.
        merged_state = {**state_with_answer, **flush_delta}
        if not _has_more_sub_inputs(merged_state):
            metadata = merged_state.get("metadata") or {}
            results = metadata.get("sub_input_results") or []
            if len(results) > 1:
                final_delta["final_answer"] = _build_aggregated_summary(results)

        return final_delta

    return format_final_answer


def _compute_per_sub_input_answer(state: AgentState) -> Dict[str, Any]:
    """The original final_answer logic, unchanged.

    Extracted from the prior `format_final_answer` body so the wrapper can
    layer sub-input bookkeeping on top without losing any branch.
    """
    # If final_answer already set (by write agent or error), use it
    if state.get("final_answer"):
        return {"final_answer": state["final_answer"]}

    # If we have an error, return it
    if state.get("error"):
        return {"final_answer": f"Error: {state['error']}"}

    # If greeting, respond friendly
    if state.get("intent") == "GREETING":
        import random
        metadata = state.get("metadata") or {}
        owner_name = str(metadata.get("owner_name") or "").strip()
        greeting_prefix = f"Hola, {owner_name}! " if owner_name else "Hola! "
        thanks_prefix = f"De nada, {owner_name}! " if owner_name else "De nada! "
        farewell_prefix = f"Chau, {owner_name}! " if owner_name else "Chau! "
        greetings = [
            f"{greeting_prefix}¿En qué te puedo ayudar hoy?",
            f"{greeting_prefix}Decime, ¿qué necesitás?",
            f"{greeting_prefix}¿Cómo te va? ¿Qué necesitás?",
            f"{greeting_prefix}Estoy acá para ayudarte con tu negocio.",
            f"{greeting_prefix}¿Querés consultar o registrar algo?",
        ]
        farewells = [
            f"{farewell_prefix}Que tengas un buen día.",
            "Hasta luego!",
            "Nos vemos! Cualquier cosa avisame.",
            f"{farewell_prefix}Acá estoy cuando necesites.",
        ]
        thanks = [
            f"{thanks_prefix}Para eso estoy.",
            "Un placer ayudarte!",
            "No hay problema! Acá estoy.",
            f"{thanks_prefix}Cualquier cosa avisame.",
        ]

        user_input_lower = state.get("user_input", "").lower()

        # Check for farewell keywords
        if any(word in user_input_lower for word in ["chau", "adiós", "adios", "bye", "hasta luego", "nos vemos"]):
            return {"final_answer": random.choice(farewells)}
        # Check for thank you keywords
        elif any(word in user_input_lower for word in ["gracias", "thank", "thanks"]):
            return {"final_answer": random.choice(thanks)}
        # Default greeting
        else:
            return {"final_answer": random.choice(greetings)}

    # If we have missing fields, ask for them
    missing = state.get("missing_fields", [])
    if missing:
        # PR-A fix #1: comma-name corruption guard from the resolver.
        # When the single REGISTER_PRODUCT branch sees a name with
        # commas or " y " connector, it appends this marker so we
        # translate it here into an explicit clarifier instead of
        # listing it as a missing field to the user.
        if "ambiguous_comma_name_split" in missing:
            entities = state.get("normalized_entities") or {}
            raw_name = (entities.get("name") or "").strip()
            hint = ""
            if raw_name:
                # Show the user the names we parsed so they can confirm
                # or correct without having to retype the whole list.
                candidates = [
                    token.strip()
                    for token in re.split(r",|\s+y\s+", raw_name)
                    if token.strip()
                ]
                if candidates:
                    hint = " (" + ", ".join(candidates) + ")"
            return {
                "final_answer": (
                    "Vi varios nombres en tu mensaje" + hint + ". "
                    "Querés que cree estos como productos separados? "
                    "Pasame la lista o decime que sea uno solo."
                )
            }
        # Translate technical field names to user-friendly Spanish
        field_translations = {
            "unit_price": "el precio de venta",
            "unit_price_cents": "el precio de venta",
            "unit_cost": "el costo de producción",
            "unit_cost_cents": "el costo de producción",
            "name": "el nombre del producto",
            "amount": "el monto",
            "amount_cents": "el monto",
            "description": "la descripción",
            "product_ref": "el producto",
            "product_id": "el producto",
            "quantity": "la cantidad",
            "items": "los productos",
            "sku": "el código del producto",
        }

        # Generic fallback so a column name we forgot to translate never
        # leaks to the user. Better to say "ese dato" than "product_id".
        friendly_missing = [field_translations.get(field, "ese dato") for field in missing]

        # Create a friendly message
        if len(friendly_missing) == 1:
            message = f"Me falta un dato: *{friendly_missing[0]}*\n\n¿Me lo podés decir?"
        else:
            fields_list = "\n• ".join(friendly_missing)
            message = f"Me faltan algunos datos:\n• {fields_list}\n\n¿Me los podés decir?"

        return {
            "final_answer": message
        }

    # If we have SQL result, return it
    if state.get("sql_result"):
        answer = state["sql_result"]
        # If we also have operation result (MIXED intent), combine them
        if state.get("operation_result"):
            write_msgs = []
            for msg in state.get("messages", []):
                # Handle both dict and LangChain message objects
                if isinstance(msg, dict):
                    content = msg.get("content", "")
                    role = msg.get("role", "")
                else:
                    content = getattr(msg, "content", "")
                    role = "assistant"

                if role == "assistant" and "[Write Agent]" in content:
                    write_msgs.append(content.replace("[Write Agent] ", ""))

            if write_msgs:
                op_msg = "\n\n".join(write_msgs)
                answer = f"{op_msg}\n\n{answer}"
        return {"final_answer": answer}

    # If AMBIGUOUS, ask for clarification
    if state.get("intent") == "AMBIGUOUS":
        return {
            "final_answer": "No estoy seguro de lo que necesitas. "
            "Aclarame si quieres consultar datos (stock, ventas, precios) "
            "o registrar algo (venta, gasto, producto nuevo, agregar stock).\n"
            "- \"Muestrame el stock actual\" (consultar)\n"
            "- \"Registra una venta de 5 pulseras\" (operacion)\n"
            "- \"Gaste 50 en envios\" (gasto)"
        }

    # If user declined a proposed product creation, ack and close.
    # Nothing is persisted (ack-and-forget by design).
    if state.get("intent") == "DECLINE_PRODUCT_CREATION":
        entities = state.get("normalized_entities") or {}
        candidate = (entities.get("candidate_name") or "").strip() or "el producto"
        return {
            "final_answer": (
                f"Ok. No registro las unidades por ahora.\n"
                f"Cuando agregues *{candidate}* al catalogo, repetimos."
            )
        }

    # Default fallback
    return {
        "final_answer": "I processed your request, but I'm not sure what to return. Please rephrase."
    }


def run_agent(user_input: str, db_path: str = "sqlite:///beansco.db", verbose: bool = True) -> str:
    """
    Run the multi-agent system on a user input.

    Args:
        user_input: User's question or command
        db_path: Database connection string
        verbose: Whether to print intermediate steps

    Returns:
        Final answer string
    """
    # Create the graph
    graph = create_business_agent_graph(db_path)

    # Initialize state
    initial_state: AgentState = {
        "messages": [],
        "user_input": user_input,
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
    }

    # Run the graph
    config = RunnableConfig(recursion_limit=50)
    result = graph.invoke(initial_state, config)

    # Print flow if verbose
    if verbose:
        print("\n" + "="*60)
        print("EXECUTION FLOW:")
        print("="*60)
        for msg in result.get("messages", []):
            # Handle both dict and LangChain message objects
            if isinstance(msg, dict):
                content = msg.get("content", "")
            else:
                # LangChain message object (AIMessage, HumanMessage, etc.)
                content = getattr(msg, "content", "")

            # Extract agent name from content (e.g., "[Router]", "[Read Agent]")
            if content.startswith("[") and "]" in content:
                agent_name = content.split("]")[0] + "]"
                message_content = content.split("]", 1)[1].strip()
                print(f"\n{agent_name}")
                print(message_content)
            else:
                print(f"\n[ASSISTANT]")
                print(content)
        print("\n" + "="*60)

    return result["final_answer"]


def interactive_mode(db_path: str = "sqlite:///beansco.db"):
    """
    Run the agent in interactive console mode.

    Args:
        db_path: Database connection string
    """
    print("=" * 60)
    print("Beans&Co Multi-Agent Business Assistant")
    print("=" * 60)
    print("\nType your question or command, or 'exit' to quit.\n")

    while True:
        try:
            user_input = input("You> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit", "q", "salir"}:
            print("Goodbye!")
            break

        try:
            answer = run_agent(user_input, db_path, verbose=True)
            print(f"\n{answer}\n")
        except Exception as e:
            print(f"\nError: {str(e)}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Beans&Co Multi-Agent Business Assistant")
    parser.add_argument("-q", "--question", help="Ask a single question and exit")
    parser.add_argument("--db", default="sqlite:///beansco.db", help="Database path")
    args = parser.parse_args()

    if args.question:
        answer = run_agent(args.question, args.db, verbose=True)
        print(f"\n{answer}\n")
    else:
        interactive_mode(args.db)
