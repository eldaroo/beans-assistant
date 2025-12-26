"""
Custom Read/Analytics Agent - Answers analytical queries using SQL SELECT statements.

Responsibilities:
- Answer analytical questions
- Execute ONLY SELECT queries
- Use views when appropriate
- Respect business rules
- NEVER execute writes
- Return human-readable explanations
"""
from typing import Dict, Any, Literal
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from database import fetch_all, fetch_one
import unicodedata

from .state import AgentState


# Entity extraction model
class ExtractedEntities(BaseModel):
    """Entities extracted from user query."""
    product_names: list[str] = Field(default_factory=list, description="Product names mentioned")
    time_period: str = Field(default="", description="Time period reference (e.g., 'última semana', 'last month', 'hoy')")
    specific_values: list = Field(default_factory=list, description="Numbers or amounts mentioned")


# Query type classification
class QueryClassification(BaseModel):
    """Classification of the user's analytical query."""
    query_type: Literal["STOCK_QUERY", "REVENUE_QUERY", "PROFIT_QUERY", "SALES_QUERY", "EXPENSE_QUERY", "PRODUCT_INFO", "GENERAL_QUERY"] = Field(
        description="Type of query based on what the user is asking"
    )
    entities: ExtractedEntities = Field(
        description="Extracted entities (product names, dates, etc.)",
        default_factory=ExtractedEntities
    )
    reasoning: str = Field(description="Brief explanation of classification")


def normalize_text(text: str) -> str:
    """Normalize text by removing accents."""
    # Remove accents
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    return text.lower()


CLASSIFIER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a query classifier for a business analytics system.

Classify the user's question into one of these types:

1. STOCK_QUERY
   - User asks about inventory, stock quantities, "cuántas tengo", "how many do I have"
   - Keywords: cuántas, cuántos, stock, inventario, tengo, quedan
   - Examples:
     * "cuántas pulseras tengo?"
     * "how much stock of black bracelets?"
     * "cuánto inventario tengo de cada producto?"

2. REVENUE_QUERY
   - User asks about sales revenue, total income, "cuánto he vendido"
   - Keywords: revenue, ingresos, vendido, facturado
   - Examples:
     * "cuánto he vendido?"
     * "what's my total revenue?"
     * "ingresos del mes"

3. PROFIT_QUERY
   - User asks about profit, gains, "cuánto he ganado"
   - Keywords: profit, ganancia, utilidad, beneficio
   - Examples:
     * "cuál es mi ganancia?"
     * "how much profit?"
     * "cuánto he ganado?"

4. SALES_QUERY
   - User asks about specific sales, sale history, transactions
   - Keywords: ventas, sales, transacciones, historial
   - Examples:
     * "qué ventas he hecho?"
     * "show me recent sales"
     * "historial de ventas"

5. EXPENSE_QUERY
   - User asks about expenses, costs, spending
   - Keywords: gastos, expenses, costos, gastado
   - Examples:
     * "cuánto he gastado?"
     * "total expenses?"
     * "gastos del mes"

6. PRODUCT_INFO
   - User asks about product details, SKUs, prices
   - Keywords: precio, price, sku, producto, catalog
   - Examples:
     * "qué productos tengo?"
     * "precio de las pulseras?"
     * "cuál es el SKU?"

7. GENERAL_QUERY
   - Any other analytical question
   - Complex queries that don't fit above categories

Extract entities:
- product_names: List of product references mentioned (e.g., ["pulseras", "negras"])
- time_period: Time/date references as string (e.g., "última semana", "last week", "hoy", "mes pasado")
  * If user says "última semana" or "last week" → "semana"
  * If user says "último mes" or "last month" → "mes"
  * If user says "hoy" or "today" → "hoy"
- specific_values: Numbers, amounts mentioned

IMPORTANT: For time_period, extract the Spanish or English phrase as-is.

Examples:
- "gastos de la última semana" → time_period: "última semana"
- "sales last month" → time_period: "last month"
- "gastos de hoy" → time_period: "hoy"

Output valid JSON only."""),
    ("user", "{input}")
])


def generate_stock_query(entities: dict) -> str:
    """
    Generate SQL for stock queries.

    Args:
        entities: Extracted entities from classification

    Returns:
        SQL query string
    """
    product_names = entities.get("product_names", [])

    if product_names:
        # Filter by specific products
        # Split product names into words and search for each word
        all_conditions = []

        for name in product_names:
            # Split into individual words
            words = name.lower().split()

            # For each word, create conditions (handle plural/singular + accents)
            word_conditions = []
            for word in words:
                # Skip common words
                if word in ["de", "granos", "cafe", "con", "la", "el", "coffee", "bean", "beans"]:
                    continue

                # Normalize and try both singular and plural forms
                word_normalized = normalize_text(word)
                word_singular = word_normalized.rstrip('s') if word_normalized.endswith('s') else word_normalized

                # Use SQL accent-insensitive matching (same as resolver)
                word_conditions.append(
                    f"(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(name), 'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o') LIKE '%{word_normalized}%' OR "
                    f"REPLACE(REPLACE(REPLACE(REPLACE(LOWER(name), 'á', 'a'), 'é', 'e'), 'í', 'i'), 'ó', 'o') LIKE '%{word_singular}%')"
                )

            # Join word conditions with AND (all words must match)
            if word_conditions:
                all_conditions.append(f"({' AND '.join(word_conditions)})")

        if all_conditions:
            where_clause = " OR ".join(all_conditions)
            return f"""
            SELECT name, stock_qty
            FROM stock_current
            WHERE {where_clause}
            ORDER BY name
            """

    # All stock (no filter or no valid conditions)
    return """
    SELECT name, stock_qty
    FROM stock_current
    ORDER BY name
    """


def generate_revenue_query(entities: dict) -> str:
    """Generate SQL for revenue queries."""
    return """
    SELECT
        total_revenue_cents / 100.0 as revenue_usd
    FROM revenue_paid
    """


def generate_profit_query(entities: dict) -> str:
    """Generate SQL for profit queries."""
    return """
    SELECT profit_usd
    FROM profit_summary
    """


def generate_sales_query(entities: dict) -> str:
    """Generate SQL for sales history queries."""
    return """
    SELECT
        s.id,
        s.sale_number,
        s.total_amount_cents / 100.0 as total_usd,
        s.status,
        s.created_at,
        GROUP_CONCAT(p.name || ' (' || si.quantity || ')') as items
    FROM sales s
    LEFT JOIN sale_items si ON s.id = si.sale_id
    LEFT JOIN products p ON si.product_id = p.id
    GROUP BY s.id
    ORDER BY s.created_at DESC
    LIMIT 10
    """


def generate_expense_query(entities: dict) -> str:
    """Generate SQL for expense queries."""
    from datetime import datetime, timedelta

    time_period = entities.get("time_period", [])

    # Build WHERE clause based on time period
    where_clause = ""
    if time_period:
        # Parse time period references
        time_ref = str(time_period).lower() if time_period else ""
        today = datetime.now().date()

        if "semana" in time_ref or "week" in time_ref:
            # Last 7 days
            start_date = (today - timedelta(days=7)).isoformat()
            where_clause = f"WHERE expense_date >= '{start_date}'"
        elif "mes" in time_ref or "month" in time_ref:
            # Last 30 days
            start_date = (today - timedelta(days=30)).isoformat()
            where_clause = f"WHERE expense_date >= '{start_date}'"
        elif "hoy" in time_ref or "today" in time_ref:
            # Today
            where_clause = f"WHERE expense_date = '{today.isoformat()}'"

    return f"""
    SELECT
        expense_date,
        category,
        description,
        amount_cents / 100.0 as amount_usd,
        created_at
    FROM expenses
    {where_clause}
    ORDER BY expense_date DESC, created_at DESC
    LIMIT 20
    """


def generate_product_info_query(entities: dict) -> str:
    """Generate SQL for product information queries."""
    return """
    SELECT
        sku,
        name,
        unit_price_cents / 100.0 as price_usd,
        unit_cost_cents / 100.0 as cost_usd
    FROM products
    WHERE is_active = 1
    ORDER BY name
    """


def format_stock_result(rows) -> str:
    """Format stock query results for user."""
    if not rows:
        return "No hay productos en el inventario."

    # Filter only bracelets (pulseras) if that's what was asked
    # Check if all results are bracelets
    bracelet_rows = [r for r in rows if "Pulsera" in r["name"]]

    if bracelet_rows and len(bracelet_rows) < len(rows):
        # User probably asked about bracelets specifically
        rows_to_show = bracelet_rows
    else:
        rows_to_show = rows

    lines = ["*📦 Stock disponible:*\n"]
    for row in rows_to_show:
        name = row["name"]
        qty = row["stock_qty"]
        lines.append(f"• {name}: *{qty}* unidades")

    return "\n".join(lines)


def format_revenue_result(rows) -> str:
    """Format revenue query results."""
    if not rows or not rows[0]:
        return "No hay ingresos registrados."

    revenue = rows[0]["revenue_usd"]
    return f"*💰 Ingresos totales:* ${revenue:,.2f}"


def format_profit_result(rows) -> str:
    """Format profit query results."""
    if not rows or not rows[0]:
        return "No hay datos de ganancia."

    profit = rows[0]["profit_usd"]
    if profit >= 0:
        return f"*📈 Ganancia total:* ${profit:,.2f}"
    else:
        return f"*📉 Pérdida total:* ${abs(profit):,.2f}"


def format_sales_result(rows) -> str:
    """Format sales history results."""
    if not rows:
        return "No hay ventas registradas."

    lines = ["*📊 Últimas ventas:*\n"]
    total_sales = 0

    for row in rows:
        total = row["total_usd"]
        total_sales += total
        status = row["status"]
        date_str = row["created_at"]
        items = row["items"] or "Productos varios"

        # Format date nicely (remove seconds and milliseconds)
        try:
            from datetime import datetime
            date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_display = date_obj.strftime("%d/%m %H:%M")
        except:
            date_display = date_str[:16]  # Fallback to truncated string

        # Translate status
        status_es = "✅" if status == "PAID" else "⏳"

        lines.append(f"• {items} - *${total:.2f}* {status_es} - _{date_display}_")

    lines.append(f"\n*Total vendido:* ${total_sales:.2f}")
    return "\n".join(lines)


def format_expense_result(rows) -> str:
    """Format expense query results."""
    if not rows:
        return "No hay gastos registrados."

    lines = ["*💸 Gastos:*\n"]
    total = 0

    for row in rows:
        # sqlite3.Row uses dict-like access
        date = row["expense_date"] if row["expense_date"] else row["created_at"]
        category = row["category"]
        description = row["description"]
        amount = row["amount_usd"]
        total += amount

        # Format date nicely (show only day/month)
        try:
            from datetime import datetime
            if isinstance(date, str):
                date_obj = datetime.fromisoformat(date.replace("Z", "+00:00"))
                date_display = date_obj.strftime("%d/%m")
            else:
                date_display = str(date)[:5]  # Just DD/MM
        except:
            date_display = str(date)[:10]  # Fallback

        # Translate category
        category_es = {
            "GENERAL": "General",
            "MATERIALS": "Materiales",
            "SHIPPING": "Envío",
            "MARKETING": "Marketing",
            "OTHER": "Otro"
        }.get(category, category)

        lines.append(f"• _{date_display}_: {description} - *${amount:.2f}*")

    lines.append(f"\n*Total gastado:* ${total:.2f}")
    return "\n".join(lines)


def format_product_info_result(rows) -> str:
    """Format product information results."""
    if not rows:
        return "No hay productos registrados."

    lines = ["*📋 Productos:*\n"]
    for row in rows:
        name = row["name"]
        price = row["price_usd"]
        lines.append(f"• {name} - *${price:.2f}*")

    return "\n".join(lines)


def create_read_agent(llm):
    """
    Create the custom read-only analytics agent.

    Args:
        llm: Language model instance

    Returns:
        Agent function that takes AgentState and returns analytical results
    """
    parser = JsonOutputParser(pydantic_object=QueryClassification)
    classifier_chain = CLASSIFIER_PROMPT | llm | parser

    def execute_read(state: AgentState) -> Dict[str, Any]:
        """
        Execute analytical query using custom logic.

        Args:
            state: Current agent state with user_input

        Returns:
            Updated state with sql_result
        """
        user_input = state["user_input"]

        # If coming from a MIXED intent and already have operation_result,
        # modify the query to reflect "after the operation"
        if state.get("operation_result"):
            user_input = f"{user_input} (after the recent operation)"

        try:
            # 1. Classify the query type
            classification = classifier_chain.invoke({"input": user_input})

            # Handle multiple possible keys (LLM sometimes uses different names)
            query_type = (classification.get("query_type") or
                         classification.get("type") or
                         classification.get("classification"))
            entities_obj = classification.get("entities", {})

            # Convert entities to dict for easier access
            if isinstance(entities_obj, dict):
                entities = entities_obj
            else:
                # If it's a Pydantic model, convert to dict
                entities = entities_obj if isinstance(entities_obj, dict) else {}

            # Fallback: if entities is empty, try to extract time_period from user_input manually
            if not entities or not entities.get("time_period"):
                user_lower = user_input.lower()
                if "semana" in user_lower or "week" in user_lower:
                    entities["time_period"] = "última semana"
                elif "mes" in user_lower or "month" in user_lower:
                    entities["time_period"] = "último mes"
                elif "hoy" in user_lower or "today" in user_lower:
                    entities["time_period"] = "hoy"

            # 2. Generate appropriate SQL based on query type
            sql_generators = {
                "STOCK_QUERY": generate_stock_query,
                "REVENUE_QUERY": generate_revenue_query,
                "PROFIT_QUERY": generate_profit_query,
                "SALES_QUERY": generate_sales_query,
                "EXPENSE_QUERY": generate_expense_query,
                "PRODUCT_INFO": generate_product_info_query,
            }

            if query_type in sql_generators:
                sql_query = sql_generators[query_type](entities)
            else:
                # GENERAL_QUERY - provide friendly guidance
                return {
                    "sql_result": """No entendí tu pregunta. ¿Podrías reformularla de forma más específica?

Puedo ayudarte con:
• Stock: "¿cuántas pulseras tengo?", "¿cuántas pulseras negras hay?"
• Ingresos: "¿cuánto he vendido?", "¿cuál es mi revenue?"
• Gastos: "¿qué gastos hice?", "¿gastos de la última semana?"
• Ganancias: "¿cuál es mi ganancia?", "¿cuánto profit tengo?"
• Ventas: "¿qué ventas he hecho?", "historial de ventas"
• Productos: "¿qué productos tengo?", "¿cuál es el precio de las pulseras?"

Por favor intenta de nuevo con una pregunta más clara.""",
                    "messages": [{
                        "role": "assistant",
                        "content": "[Read Agent] Clarification needed"
                    }]
                }

            # 3. Execute SQL
            rows = fetch_all(sql_query)

            # 4. Format results based on query type
            formatters = {
                "STOCK_QUERY": format_stock_result,
                "REVENUE_QUERY": format_revenue_result,
                "PROFIT_QUERY": format_profit_result,
                "SALES_QUERY": format_sales_result,
                "EXPENSE_QUERY": format_expense_result,
                "PRODUCT_INFO": format_product_info_result,
            }

            formatted_result = formatters[query_type](rows)

            return {
                "sql_result": formatted_result,
                "messages": [{
                    "role": "assistant",
                    "content": f"[Read Agent] {formatted_result}"
                }]
            }

        except Exception as e:
            error_msg = f"Read agent error: {str(e)}"
            import traceback
            traceback.print_exc()

            # Provide friendly error message to user
            friendly_error = """Disculpa, tuve un problema procesando tu pregunta.

¿Podrías intentar reformularla? Puedo ayudarte con:
• Stock de productos
• Ingresos y ganancias
• Gastos y categorías
• Historial de ventas
• Información de productos"""

            return {
                "sql_result": friendly_error,
                "error": error_msg,
                "messages": [{
                    "role": "assistant",
                    "content": f"[Read Agent] Error - {error_msg}"
                }]
            }

    return execute_read
