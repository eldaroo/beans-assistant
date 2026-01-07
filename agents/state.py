"""
Shared state definition for the multi-agent LangGraph system.
This state is passed between all agents in the workflow.
"""
from typing import TypedDict, Literal, Optional, List, Dict, Any
from typing_extensions import Annotated
from langgraph.graph.message import add_messages


# Intent types
IntentType = Literal[
    "READ_ANALYTICS",      # Analytical queries (SELECT only)
    "WRITE_OPERATION",     # Business operations (register_sale, etc.)
    "MIXED",               # Both write then read
    "GREETING",            # Casual greetings and conversation
    "AMBIGUOUS"            # Needs clarification
]

# Operation types for WRITE_OPERATION
OperationType = Literal[
    "REGISTER_SALE",
    "REGISTER_EXPENSE",
    "REGISTER_PRODUCT",
    "ADD_STOCK",
    "UNKNOWN"
]


class AgentState(TypedDict):
    """
    Shared state passed between all agents in the graph.

    Fields:
    - messages: Accumulated conversation messages
    - user_input: Original user input
    - intent: Classified intent (READ_ANALYTICS, WRITE_OPERATION, MIXED, AMBIGUOUS)
    - operation_type: Specific operation type if WRITE_OPERATION
    - confidence: Classification confidence score (0-1)
    - missing_fields: List of missing required fields
    - normalized_entities: Resolved entities (SKU, product_id, dates, etc.)
    - sql_result: Result from read agent
    - operation_result: Result from write agent
    - final_answer: Final response to user
    - error: Error message if any step failed
    - next_action: Next step in the workflow
    """
    # Core
    messages: Annotated[List[Dict[str, Any]], add_messages]
    user_input: str

    # Intent classification
    intent: Optional[IntentType]
    operation_type: Optional[OperationType]
    confidence: Optional[float]
    missing_fields: List[str]

    # Entity resolution
    normalized_entities: Dict[str, Any]

    # Agent results
    sql_result: Optional[str]
    operation_result: Optional[Dict[str, Any]]
    final_answer: Optional[str]

    # Error handling
    error: Optional[str]

    # Flow control
    next_action: Optional[str]
