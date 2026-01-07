"""
LangGraph Multi-Agent Orchestration for Beans&Co Business Agent.

This module defines the complete workflow graph that routes user requests
through specialized agents based on intent classification.

Flow:
    User Input → Router → [Read Agent | Resolver → Write Agent → (Read Agent)] → Final Answer
"""
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from agents import (
    AgentState,
    create_router_agent,
    create_read_agent,
    create_write_agent,
    create_resolver_agent,
    route_to_next_node,
    route_after_write,
    route_after_resolver,
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
    llm_cheap = get_llm_cheap()  # Cheap LLM for resolver disambiguation

    # Create specialized agents
    router = create_router_agent(llm)
    read_agent = create_read_agent(llm)  # Custom read agent (no db_path needed)
    write_agent = create_write_agent()
    resolver = create_resolver_agent(llm_cheap)  # Use cheap LLM for product disambiguation

    # Define the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("router", router)
    workflow.add_node("read_agent", read_agent)
    workflow.add_node("write_agent", write_agent)
    workflow.add_node("resolver", resolver)
    workflow.add_node("final_answer", create_final_answer_node())

    # Set entry point
    workflow.set_entry_point("router")

    # Add conditional edges from router
    workflow.add_conditional_edges(
        "router",
        route_to_next_node,
        {
            "read_agent": "read_agent",
            "resolver": "resolver",
            "final_answer": "final_answer",
        }
    )

    # Add conditional edges from resolver
    workflow.add_conditional_edges(
        "resolver",
        route_after_resolver,
        {
            "write_agent": "write_agent",
            "final_answer": "final_answer",
        }
    )

    # Add conditional edges from write_agent
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

    # Final answer goes to END
    workflow.add_edge("final_answer", END)

    # Compile the graph
    return workflow.compile()


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
        # If final_answer already set (by write agent or error), use it
        if state.get("final_answer"):
            return {"final_answer": state["final_answer"]}

        # If we have an error, return it
        if state.get("error"):
            return {"final_answer": f"Error: {state['error']}"}

        # If greeting, respond friendly
        if state.get("intent") == "GREETING":
            import random
            greetings = [
                "Hola! ¿En qué te puedo ayudar hoy?",
                "Hola! Decime, ¿qué necesitás?",
                "Hola! ¿Cómo te va? ¿Qué necesitás?",
                "Hola! Estoy acá para ayudarte con tu negocio.",
                "Hola! ¿Querés consultar o registrar algo?",
            ]
            farewells = [
                "Chau! Que tengas un buen día.",
                "Hasta luego!",
                "Nos vemos! Cualquier cosa avisame.",
                "Chau! Acá estoy cuando necesites.",
            ]
            thanks = [
                "De nada! Para eso estoy.",
                "Un placer ayudarte!",
                "No hay problema! Acá estoy.",
                "De nada! Cualquier cosa avisame.",
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
                "quantity": "la cantidad",
                "items": "los productos",
                "sku": "el código del producto",
            }

            friendly_missing = [field_translations.get(field, field) for field in missing]

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

        # Default fallback
        return {
            "final_answer": "I processed your request, but I'm not sure what to return. Please rephrase."
        }

    return format_final_answer


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
