import argparse

from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain_core.tools import Tool

from llm import get_llm
from database import (
    register_product,
    add_stock,
    register_sale,
)

# =========================
# PROMPT
# =========================

PROMPT_TEMPLATE = """
You are a senior SQL analyst working with a SQLite database for a small business (Beans&Co).

Use only the listed database objects.

ABSOLUTE SQL OUTPUT RULE (NON-NEGOTIABLE):

When using Action: sql_db_query
- Output ONLY plain SQL text
- DO NOT include backticks, markdown, tool_code, or code fences
- DO NOT repeat the same query multiple times
- One SQL query → one Action → then Final Answer

After a successful SQL query:
- You MUST stop querying
- You MUST produce a Final Answer
- Never retry the same query unless it failed

If you include markdown or code fences, the execution will fail.

INTENT CLASSIFICATION (MANDATORY):

Before taking any action, you MUST classify the user request as ONE of:

A) Analytical question (read-only, metrics, counts, stock, revenue, profit)
B) Business operation (registering a sale, adding stock, creating a product)

If the request is a Business operation:
- You MUST NOT use sql_db_query or sql_db_schema.
- You MUST NOT generate or attempt SQL.
- You MUST use the appropriate business action tool directly.
- You MUST rely on the tool to resolve SKUs, IDs, pricing, and validation.

Attempting SQL for a business operation is a critical error.

Business operation keywords include (not exhaustive):
- registrar
- registrame
- crear
- agregar
- vender
- venta
- descontar stock
- cargar producto

For sales registration:
- The agent MUST pass items using SKU and quantity.
- The agent MUST NOT attempt to look up product IDs.
- Product resolution is handled inside the business action.

Database objects:
expenses, products, sale_items, sales, stock_movements
(Additional objects of type VIEW may exist and must be preferred when applicable.)

STRICT BUSINESS RULES (MANDATORY):

1. Stock calculation
- Stock MUST be computed ONLY from stock_movements.
- NEVER join stock_movements with sales or sale_items.
- Stock depends exclusively on movement_type and quantity.
- Mixing stock with sales data is a critical error.

2. Profit calculation
- Profit is a GLOBAL business metric.
- Profit = Revenue (PAID sales) − Expenses.
- Profit MUST NOT be calculated from unit_price, unit_cost, or sale_items.
- If a view related to profit exists (e.g. profit_summary), it MUST be used.
- Recomputing profit from base tables when a view exists is an error.

3. Views usage
- Objects of type VIEW represent canonical business metrics.
- If a requested metric exists as a view, you MUST query the view.
- Do NOT recreate business logic already expressed in a view.

SQL rules:
- Only SELECT statements for analytical queries.
- Never use SELECT *.
- Do not guess table or column names.
- Use correct GROUP BY semantics.

Analytical guidance:
- Stock and profit are independent metrics.
- Do NOT attempt to compute them in a single query.
- Prefer multiple simple queries over one complex query.
- Do NOT assume that natural language terms used by the user
  (e.g. "pulseras", "bracelets", "productos")
  match text values stored in the database.
- When filtering by product type or category, prefer:
  - SKU patterns
  - explicit columns
  - structural relationships
  over free-text matching on names or descriptions.
- If the user asks in a different language than the stored data,
  reason over the data model instead of translating values literally.

Formatting rules:
- You MUST follow the ReAct format.
- Never output raw SQL unless executing it via an Action.
- When executing SQL, always use:
  Action: sql_db_query
  Action Input: <SQL query>
- Only output Final Answer after all actions are completed.

CRITICAL SQL FORMATTING RULES:
- When executing SQL, output ONLY raw SQL.
- NEVER include markdown, backticks, or ```sql fences.
- Action Input must contain plain SQL text only.
- Including ``` or markdown is a critical error.

AUTHORITATIVE VIEW SCHEMAS (DO NOT INFER):

stock_current:
- product_id (INTEGER)
- sku (TEXT)
- name (TEXT)
- stock_qty (INTEGER)
Note: Includes ALL active products, even those with 0 stock.

profit_summary:
- profit_usd (REAL)

revenue_paid:
- total_revenue_cents (INTEGER)

expenses_total:
- total_expenses_cents (INTEGER)

Do NOT inspect sqlite_master to infer view schemas.
These schemas are authoritative.

────────────────────────────────────────
CONTROLLED WRITE OPERATIONS (ADDITIVE)

- You are allowed to register business operations that modify data.
- Write operations are ONLY allowed through explicitly provided business actions (tools).
- You must NEVER generate raw SQL INSERT, UPDATE, or DELETE statements.

Before executing a write action:
- Briefly explain what business event will be recorded.
- Ensure all required information is present.

After executing a write action:
- Summarize the business impact.

All analytical rules above remain unchanged.
────────────────────────────────────────

Respond with a concise, human-readable explanation of the result.
"""


# =========================
# HELPERS
# =========================

def run_agent_query(agent, system_prompt: str, question: str):
    """
    Run agent query with error handling.

    Args:
        agent: SQL agent instance
        system_prompt: System prompt template
        question: User question

    Returns:
        Agent response string
    """
    prompt = f"{system_prompt}\n\nQuestion: {question}"

    try:
        result = agent.invoke(prompt)
        return result["output"] if isinstance(result, dict) and "output" in result else result
    except Exception as e:
        # Log the error for debugging
        print(f"\n[ERROR] Agent execution failed: {str(e)}")
        import traceback
        traceback.print_exc()

        # Return a user-friendly error message
        error_msg = str(e)
        if "No hay suficiente stock" in error_msg:
            return f"⚠️ {error_msg}\n\nPor favor verifica el inventario disponible antes de registrar la venta."
        elif "Unknown product" in error_msg or "no encontrado" in error_msg:
            return f"⚠️ {error_msg}\n\nPor favor verifica que el producto exista en el catálogo."
        elif "output parsing error" in error_msg.lower() or "I don't know" in error_msg:
            return "⚠️ No pude entender tu pregunta.\n\nPor favor reformula tu pregunta sobre el negocio (ventas, stock, productos, gastos, ganancias, etc.)"
        else:
            return f"⚠️ Lo siento, ocurrió un error al procesar tu solicitud:\n{error_msg}\n\nPor favor intenta de nuevo o reformula tu pregunta."


def interactive_console(agent, system_prompt: str):
    print("SQL agent ready. Type your question or 'exit' to quit.")
    while True:
        try:
            question = input("\nQuestion> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not question:
            continue
        if question.lower() in {"exit", "quit", "q", "salir"}:
            print("Bye.")
            break

        res = run_agent_query(agent, system_prompt, question)
        print("\n=== RESULT ===")
        print(res)


# =========================
# MAIN
# =========================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-q",
        "--question",
        help="Ask a single question and exit. If omitted, interactive mode starts.",
    )
    args = parser.parse_args()

    llm = get_llm()

    # 🔹 DB se crea directamente (no get_database)
    db = SQLDatabase.from_uri("sqlite:///beansco.db")

    # 🔹 Business actions como tools
    tools = [
        Tool(
            name="register_product",
            description="Register a new product in the catalog",
            func=register_product,
        ),
        Tool(
            name="add_stock",
            description="Add or adjust stock for a product",
            func=add_stock,
        ),
        Tool(
            name="register_sale",
            description="Register a sale and update stock if paid",
            func=register_sale,
        ),
    ]

    agent = create_sql_agent(
        llm=llm,
        db=db,
        extra_tools=tools,
        system_message=PROMPT_TEMPLATE,
        verbose=True,
        handle_parsing_errors=True,
    )

    if args.question:
        res = run_agent_query(agent, PROMPT_TEMPLATE, args.question)
        print("\n=== RESULT ===")
        print(res)
    else:
        interactive_console(agent, PROMPT_TEMPLATE)


if __name__ == "__main__":
    main()
