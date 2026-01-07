"""
Intent Router Agent - Classifies user intent without executing any tools.

Responsibilities:
- Analyze user input (Spanish or English)
- Classify intent as READ_ANALYTICS, WRITE_OPERATION, MIXED, or AMBIGUOUS
- Extract and normalize entities
- Identify missing required fields
- NO SQL execution
- NO database writes
"""
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from .state import AgentState


class IntentClassification(BaseModel):
    """Structured output for intent classification."""
    intent: str = Field(description="Intent type: READ_ANALYTICS, WRITE_OPERATION, MIXED, GREETING, or AMBIGUOUS")
    operation_type: str = Field(description="For WRITE_OPERATION: REGISTER_SALE, REGISTER_EXPENSE, REGISTER_PRODUCT, ADD_STOCK, CANCEL_SALE, CANCEL_EXPENSE, CANCEL_STOCK, CANCEL_LAST_OPERATION, DEACTIVATE_PRODUCT, or UNKNOWN")
    confidence: float = Field(description="Confidence score between 0 and 1")
    missing_fields: list[str] = Field(description="List of missing required fields")
    normalized_entities: dict = Field(description="Extracted entities with normalized values")
    reasoning: str = Field(description="Brief explanation of classification decision")


ROUTER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an Intent Router for a business management system (Beans&Co).

Your ONLY job is to classify user intent. You DO NOT execute queries or operations.

IMPORTANT CONVERSATION CONTEXT:
- The user input may include "Contexto de conversación reciente:" followed by previous messages
- You MUST extract entities from BOTH the conversation context AND the current message
- If the context mentions a product name and the current message mentions a price, combine both
- Example:
  Context: "Usuario: registrar Pulseras Premium"
  Current: "salen 10 dólares"
  → Extract: {{"name": "Pulseras Premium", "unit_price": 10}}

INTENT CATEGORIES:

1. READ_ANALYTICS
   - User wants to know/analyze/check/see data
   - Keywords: cuánto, cuántos, cómo está, stock, revenue, profit, ventas, productos
   - Examples:
     * "¿cuántas pulseras tengo?"
     * "what's my total revenue?"
     * "show me profit"
     * "cuánto stock tengo de cada producto"

2. WRITE_OPERATION
   - User wants to register/record/create/add/cancel something
   - Keywords: registrar, registrame, crear, agregar, vender, venta, gasté, compré, cancelar, anular, borrar
   - Operation types:
     * REGISTER_SALE: "vendí X", "registrame una venta"
     * REGISTER_EXPENSE: "gasté X", "registrar gasto"
     * REGISTER_PRODUCT: "crear producto", "nuevo producto", "nuevas pulseras", "nuevo tipo de"
       - IMPORTANT: If user says "nuevas/nuevo" → REGISTER_PRODUCT (not ADD_STOCK)
     * ADD_STOCK: "agregar stock" (WITHOUT "nuevo/nueva"), "añadir inventario", "agrego 10 pulseras" (to existing product)
       - IMPORTANT: Only ADD_STOCK if adding to EXISTING product, not creating new one
     * CANCEL_SALE: "cancela la venta", "anula la última venta", "borra esa venta"
     * CANCEL_EXPENSE: "cancela el gasto", "anula ese gasto", "borra el último gasto"
     * CANCEL_STOCK: "cancela el stock", "anula el stock", "revertí el stock"
     * CANCEL_LAST_OPERATION: "anula la última operación", "cancela lo último", "borra lo último que hice"
       - IMPORTANT: Use this when user says "última operación" without specifying if it's sale/expense/stock
     * DEACTIVATE_PRODUCT: "eliminar producto", "borrar producto", "desactivar producto", "sacar producto"
       - IMPORTANT: This deactivates a product (not deleting data, just marking as inactive)
       - Use when user wants to remove a product from catalog
   - Examples:
     * "registrame una venta de 20 pulseras negras"
     * "gasté 30 dólares en envíos"
     * "vendí 2 pulseras black"
     * "agrego unas NUEVAS pulseras arcoiris" → REGISTER_PRODUCT (keyword: "nuevas")
     * "agrego 10 pulseras negras" → ADD_STOCK (adding to existing product)
     * "cancela la última venta"
     * "anula el gasto que acabo de hacer"
     * "eliminá las pulseras nuevas" → DEACTIVATE_PRODUCT
     * "borra el producto X" → DEACTIVATE_PRODUCT

3. MIXED
   - User wants to do a write operation AND then see the result
   - Usually combines action + question
   - Examples:
     * "vendí 2 pulseras black, ¿cómo queda el stock?"
     * "registra la venta y dime el nuevo revenue"

4. GREETING
   - Casual greetings, small talk, gratitude, farewells
   - No business intent, just social interaction
   - Keywords: hola, hey, hi, hello, buenos días, buenas tardes, qué tal, cómo estás, gracias, thank you, chau, adiós, bye
   - Examples:
     * "hola!"
     * "buenos días"
     * "hey, cómo andas?"
     * "gracias!"
     * "chau"
     * "hi there"
   - IMPORTANT: Respond naturally and friendly, keep it brief

5. AMBIGUOUS
   - Missing critical information
   - Unclear intent
   - Examples:
     * "registrar algo" (what?)
     * "cuánto tengo" (of what?)

ENTITY EXTRACTION:

Extract and normalize:
- product_ref: Product references (SKUs, names like "pulseras negras", "black bracelet")
- quantity: Numbers
- unit_price: Custom price per unit (e.g., "a 5 dólares", "at $10 each", "$12 cada una")
  * If user specifies a price, extract it as unit_price in USD
  * This will override the catalog price
- amount: Total money amounts for expenses
- date: Time references ("ayer", "yesterday", specific dates)
- status: Payment status (PAID, PENDING)

IMPORTANT FOR PRICES:
- If user says "a 5 dólares", "at $5", "por 10 dólares": extract as unit_price: 5 (or 10)
- If user says "5 dólares cada una": extract as unit_price: 5
- If user says "el precio es de $10", "cuesta $15", "sale $20": extract as unit_price: 10 (or 15, or 20)
- For REGISTER_PRODUCT: extract "precio" or "price" as unit_price
- Store prices in USD (not cents) in normalized_entities
- Example: "venta de 3 pulseras a 10 dólares" → {{"items": [{{"product_ref": "pulseras", "quantity": 3, "unit_price": 10}}]}}
- Example: "crear producto Pulseras Verdes, el precio es de $10" → {{"name": "Pulseras Verdes", "unit_price": 10}}

MISSING FIELDS:

For WRITE_OPERATION, identify if required fields are missing:
- REGISTER_SALE: needs items (product_ref + quantity)
- REGISTER_EXPENSE: needs amount and description
- REGISTER_PRODUCT: needs name and unit_price (sku and cost are auto-generated/optional)
- ADD_STOCK: needs items (product_ref + quantity) OR single product_ref and quantity
  * Can handle MULTIPLE products in one message using items array
  * Example: "entraron 400 clasicas y 200 doradas" → {{"items": [{{"product_ref": "clasicas", "quantity": 400}}, {{"product_ref": "doradas", "quantity": 200}}]}}
  * Example: "agregar 50 pulseras negras" → {{"product_ref": "pulseras negras", "quantity": 50}}
- CANCEL_SALE: needs target ("last" or sale_id) - extract "last", "última", "ese", "esa" as target: "last"
- CANCEL_EXPENSE: needs target ("last" or expense_id) - extract "last", "última", "último", "ese", "esa" as target: "last"
- DEACTIVATE_PRODUCT: needs product_ref (product name or SKU to deactivate)
  * Example: "eliminá las pulseras nuevas" → {{"product_ref": "pulseras nuevas"}}

OUTPUT FORMAT:

Return valid JSON with this structure:
{{
  "intent": "WRITE_OPERATION",
  "operation_type": "REGISTER_SALE",
  "confidence": 0.95,
  "missing_fields": [],
  "normalized_entities": {{
    "items": [
      {{"product_ref": "pulseras negras", "quantity": 20}}
    ]
  }},
  "reasoning": "User explicitly says 'registrame una venta' with product and quantity"
}}

CONVERSATION CONTEXT EXAMPLES:

Example 1 (Multi-turn product creation):
Input:
```
Contexto de conversación reciente:
Usuario: voy a registrar un nuevo tipo de pulseras, tienen piedras preciosas. Les llamo Pulseras Premium
Asistente: Necesito más información para completar esta solicitud. Falta: unit_price

Mensaje actual: salen 10 dolares
```
Output:
{{
  "intent": "WRITE_OPERATION",
  "operation_type": "REGISTER_PRODUCT",
  "confidence": 0.95,
  "missing_fields": [],
  "normalized_entities": {{
    "name": "Pulseras Premium",
    "unit_price": 10
  }},
  "reasoning": "Context provides product name 'Pulseras Premium', current message provides price $10"
}}

Example 2 (Follow-up question):
Input:
```
Contexto de conversación reciente:
Usuario: vendí 10 pulseras negras
Asistente: Venta registrada exitosamente!

Mensaje actual: cuanto stock me queda?
```
Output:
{{
  "intent": "READ_ANALYTICS",
  "operation_type": "UNKNOWN",
  "confidence": 0.9,
  "missing_fields": [],
  "normalized_entities": {{}},
  "reasoning": "User asking about remaining stock after a sale"
}}

IMPORTANT:
- DO NOT execute SQL
- DO NOT write to database
- DO NOT resolve product IDs (that's the resolver's job)
- ONLY classify and extract entities from natural language"""),
    ("user", "{input}")
])


def create_router_agent(llm):
    """
    Create the router agent that classifies user intent.

    Args:
        llm: Language model instance

    Returns:
        Agent function that takes AgentState and returns classification
    """
    parser = JsonOutputParser(pydantic_object=IntentClassification)
    chain = ROUTER_PROMPT | llm | parser

    def route_intent(state: AgentState) -> Dict[str, Any]:
        """
        Classify user intent and extract entities.

        Args:
            state: Current agent state

        Returns:
            Updated state with intent classification
        """
        user_input = state["user_input"]

        try:
            result = chain.invoke({"input": user_input})

            # If classification is low confidence, ask for clarification instead of guessing
            if result["confidence"] < 0.6:
                clarification = (
                    "Tengo dudas sobre lo que necesitas. "
                    "Puedes decirme si quieres consultar datos (stock, ventas, precios) "
                    "o registrar algo (venta, gasto, producto nuevo, agregar stock)?"
                )
                return {
                    "intent": "AMBIGUOUS",
                    "operation_type": result.get("operation_type", "UNKNOWN"),
                    "confidence": result["confidence"],
                    "missing_fields": [],
                    "normalized_entities": result.get("normalized_entities", {}),
                    "final_answer": clarification,
                    "messages": [{
                        "role": "assistant",
                        "content": f"[Router] Confianza baja ({result['confidence']:.2f}). Pido aclaracion al usuario."
                    }]
                }

            return {
                "intent": result["intent"],
                "operation_type": result.get("operation_type", "UNKNOWN"),
                "confidence": result["confidence"],
                "missing_fields": result.get("missing_fields", []),
                "normalized_entities": result.get("normalized_entities", {}),
                "messages": [{
                    "role": "assistant",
                    "content": f"[Router] Intent classified as {result['intent']}. Reasoning: {result.get('reasoning', 'N/A')}"
                }]
            }

        except Exception as e:
            # Debug: print the actual error
            import traceback
            print(f"\n!!! ROUTER ERROR !!!")
            print(f"Error: {str(e)}")
            print(f"Traceback:")
            traceback.print_exc()
            print(f"!!! END ERROR !!!\n")

            return {
                "intent": "AMBIGUOUS",
                "confidence": 0.0,
                "error": f"Router failed: {str(e)}",
                "missing_fields": [],
                "normalized_entities": {}
            }

    return route_intent


def route_to_next_node(state: AgentState) -> str:
    """
    Determine next node based on intent classification.

    Args:
        state: Current agent state

    Returns:
        Name of next node to execute
    """
    intent = state.get("intent")
    missing_fields = state.get("missing_fields", [])

    # If there's an error, go to final answer
    if state.get("error"):
        return "final_answer"

    # If greeting, respond immediately with friendly message
    if intent == "GREETING":
        return "final_answer"

    # If ambiguous or missing fields, ask for clarification
    if intent == "AMBIGUOUS" or missing_fields:
        return "final_answer"  # Return clarification question

    # If read analytics, go to read agent
    if intent == "READ_ANALYTICS":
        return "read_agent"

    # If write operation, first resolve entities, then write
    if intent == "WRITE_OPERATION":
        return "resolver"

    # If mixed, go to write first (resolver will handle it)
    if intent == "MIXED":
        return "resolver"

    # Default: final answer
    return "final_answer"
