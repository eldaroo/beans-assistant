# Beans&Co Multi-Agent Architecture

## Overview

This is a **multi-agent system** built with **LangGraph** that separates responsibilities across specialized agents for managing a small business (Beans&Co). The system handles both analytical queries and business operations through a clean, orchestrated workflow.

## Core Principles

1. **Separation of Concerns**: Each agent has a single, well-defined responsibility
2. **No Overlapping Capabilities**: Read agents can't write, write agents can't read SQL
3. **Explicit Intent Classification**: Router decides the flow, agents execute
4. **Stateful Orchestration**: Shared state (TypedDict) flows through the graph
5. **Scalable Design**: Easy to add new agents or operations

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER INPUT                                  │
│                     (Spanish or English)                             │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
         ┌────────────────────────────┐
         │   INTENT ROUTER AGENT      │
         │  (Classification Only)     │
         │                            │
         │ - Analyze input            │
         │ - Classify intent          │
         │ - Extract entities         │
         │ - NO SQL, NO writes        │
         └────────────┬───────────────┘
                      │
                      ├─────────────────────────────────────┐
                      │                                     │
                      ▼                                     ▼
         ┌────────────────────────┐          ┌─────────────────────────┐
         │   READ_ANALYTICS       │          │  WRITE_OPERATION        │
         │                        │          │       or MIXED          │
         └──────┬─────────────────┘          └─────────┬───────────────┘
                │                                      │
                ▼                                      ▼
    ┌───────────────────────┐           ┌──────────────────────────────┐
    │  READ/ANALYTICS       │           │  NORMALIZATION/RESOLVER      │
    │      AGENT            │           │         AGENT                │
    │                       │           │                              │
    │ - SQL SELECT only     │           │ - Resolve product refs       │
    │ - Use views           │           │ - Normalize dates            │
    │ - Business rules      │           │ - Simple DB lookups          │
    │ - NO writes           │           │ - NO writes                  │
    └──────┬────────────────┘           └──────────┬───────────────────┘
           │                                       │
           │                                       ▼
           │                          ┌──────────────────────────────┐
           │                          │  WRITE/OPERATIONS AGENT      │
           │                          │                              │
           │                          │ - register_sale()            │
           │                          │ - register_expense()         │
           │                          │ - register_product()         │
           │                          │ - add_stock()                │
           │                          │ - NO raw SQL                 │
           │                          └──────────┬───────────────────┘
           │                                     │
           │                                     │ (if MIXED intent)
           │                                     ▼
           │                          ┌──────────────────────────────┐
           │                          │  READ/ANALYTICS AGENT        │
           │                          │  (Re-check after operation)  │
           │                          └──────────┬───────────────────┘
           │                                     │
           └─────────────────┬───────────────────┘
                             │
                             ▼
                ┌────────────────────────┐
                │   FINAL ANSWER NODE    │
                │  (Format Response)     │
                └────────────┬───────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │      END       │
                    └────────────────┘
```

---

## Agent Specifications

### 1. Intent Router Agent

**File**: `agents/router.py`

**Responsibilities**:
- Analyze user input (Spanish or English)
- Classify intent as:
  - `READ_ANALYTICS`: Questions about data (stock, revenue, profit, etc.)
  - `WRITE_OPERATION`: Register sale, expense, product, stock
  - `MIXED`: Write operation followed by read (e.g., "sell 2 bracelets and show me stock")
  - `AMBIGUOUS`: Missing information or unclear intent
- Extract entities (product references, quantities, dates, amounts)
- Identify missing required fields

**Constraints**:
- NO SQL execution
- NO database writes
- NO final decisions (only classification)

**Output**:
```python
{
  "intent": "WRITE_OPERATION",
  "operation_type": "REGISTER_SALE",
  "confidence": 0.92,
  "missing_fields": [],
  "normalized_entities": {
    "items": [{"product_ref": "pulseras negras", "quantity": 20}]
  }
}
```

---

### 2. Read/Analytics Agent

**File**: `agents/read_agent.py`

**Responsibilities**:
- Answer analytical questions
- Execute ONLY `SELECT` queries
- Use views when they exist (e.g., `stock_current`, `profit_summary`)
- Respect strict business rules:
  - Stock from `stock_movements` ONLY
  - Profit from `profit_summary` view
  - No mixing of stock and sales tables
- Return human-readable explanations

**Constraints**:
- NO `INSERT`, `UPDATE`, `DELETE`
- NO business action tools
- Uses the same strict SQL prompt from the original system

**Example Queries**:
- "How many bracelets do I have?"
- "What's my total revenue?"
- "Show me profit"

---

### 3. Write/Operations Agent

**File**: `agents/write_agent.py`

**Responsibilities**:
- Execute business operations through Python functions:
  - `register_sale(data)`
  - `register_expense(data)` (needs implementation)
  - `register_product(data)`
  - `add_stock(data)`
- Validate required fields before execution
- Summarize business impact (stock changes, revenue, profit)

**Constraints**:
- NO raw SQL generation
- NO `sql_db_query` tool
- Only calls explicit Python functions
- Must validate all required data before executing

**Example Operations**:
- "Register a sale of 20 black bracelets"
- "I spent $30 on shipping yesterday"
- "Add 50 units to product BC-BRACELET-BLACK"

---

### 4. Normalization/Resolver Agent

**File**: `agents/resolver.py`

**Responsibilities**:
- Resolve human references to database entities:
  - "pulseras negras" → SKU or product_id
  - "ayer" → ISO date (yesterday's date)
  - "la más barata" → auxiliary query
- Perform simple database lookups (read-only)
- Validate required fields for each operation type
- Flag missing or unresolvable entities

**Constraints**:
- NO writes
- NO final decisions
- Helper agent for Write and Read agents

**Example Resolutions**:
- `"pulseras negras"` → `product_id: 1, sku: "BC-BRACELET-BLACK"`
- `"ayer"` → `"2024-12-24"`
- `"$30"` → `3000` (cents)

---

## State Management

All agents share a **typed state** (`AgentState`) that flows through the graph:

```python
class AgentState(TypedDict):
    # Core
    messages: List[Dict[str, Any]]       # Message history
    user_input: str                      # Original user input

    # Intent classification
    intent: Optional[IntentType]         # READ_ANALYTICS, WRITE_OPERATION, etc.
    operation_type: Optional[OperationType]  # REGISTER_SALE, ADD_STOCK, etc.
    confidence: float                    # Classification confidence (0-1)
    missing_fields: List[str]            # Missing required data

    # Entity resolution
    normalized_entities: Dict[str, Any]  # Resolved entities (SKU, dates, etc.)

    # Agent results
    sql_result: Optional[str]            # Result from read agent
    operation_result: Optional[Dict]     # Result from write agent
    final_answer: Optional[str]          # Final response to user

    # Error handling
    error: Optional[str]                 # Error message if any

    # Flow control
    next_action: Optional[str]           # Next step in workflow
```

---

## Workflow Examples

### Example 1: Analytical Query (READ_ANALYTICS)

**User Input**: "¿cuántas pulseras tengo de cada tipo?"

**Flow**:
1. **Router**: Classifies as `READ_ANALYTICS`
2. **Read Agent**: Executes `SELECT sku, name, stock_qty FROM stock_current WHERE sku LIKE '%BRACELET%'`
3. **Final Answer**: "You have: BC-BRACELET-BLACK (15 units), BC-BRACELET-WHITE (8 units)"

**Diagram**:
```
User → Router → Read Agent → Final Answer
```

---

### Example 2: Write Operation (WRITE_OPERATION)

**User Input**: "registrame una venta de 20 pulseras negras"

**Flow**:
1. **Router**: Classifies as `WRITE_OPERATION` / `REGISTER_SALE`
   - Entities: `{"items": [{"product_ref": "pulseras negras", "quantity": 20}]}`
2. **Resolver**:
   - Resolves "pulseras negras" → `product_id: 1, sku: BC-BRACELET-BLACK`
3. **Write Agent**: Calls `register_sale({"items": [{"product_id": 1, "quantity": 20}]})`
   - Returns: `{"sale_id": 123, "total_usd": 40.00, "revenue_usd": 1500.00}`
4. **Final Answer**: "✓ Sale registered (ID: 123, Total: $40.00). Current revenue: $1500.00"

**Diagram**:
```
User → Router → Resolver → Write Agent → Final Answer
```

---

### Example 3: Mixed Operation (MIXED)

**User Input**: "vendí 2 pulseras black, ¿cómo queda el stock?"

**Flow**:
1. **Router**: Classifies as `MIXED`
2. **Resolver**: Resolves "pulseras black" → `product_id: 1`
3. **Write Agent**: Executes `register_sale(...)`
4. **Read Agent**: Queries `SELECT stock_qty FROM stock_current WHERE product_id = 1`
5. **Final Answer**: Combines both:
   - "✓ Sale registered (ID: 124, Total: $4.00)"
   - "Current stock for BC-BRACELET-BLACK: 13 units"

**Diagram**:
```
User → Router → Resolver → Write Agent → Read Agent → Final Answer
```

---

## File Structure

```
supabase-sql-agent/
├── agents/
│   ├── __init__.py           # Package exports
│   ├── state.py              # Typed state definition
│   ├── router.py             # Intent Router Agent
│   ├── read_agent.py         # Read/Analytics Agent
│   ├── write_agent.py        # Write/Operations Agent
│   └── resolver.py           # Normalization/Resolver Agent
├── graph.py                  # LangGraph orchestration
├── database.py               # Business action functions
├── llm.py                    # LLM configuration
├── example_usage.py          # Example test cases
├── ARCHITECTURE.md           # This file
└── README.md                 # Project README
```

---

## Running the System

### Interactive Mode

```bash
python graph.py
```

This starts an interactive console where you can type questions or commands.

### Single Query

```bash
python graph.py -q "cuántas pulseras tengo?"
```

### Run Examples

```bash
python example_usage.py          # Run all tests
python example_usage.py read     # Test analytical queries
python example_usage.py write    # Test write operations
python example_usage.py mixed    # Test mixed operations
python example_usage.py full     # Full verbose flow
```

---

## Adding New Functionality

### Add a New Operation Type

1. **Add to `state.py`**:
   ```python
   OperationType = Literal[
       "REGISTER_SALE",
       "REGISTER_EXPENSE",
       "REGISTER_PRODUCT",
       "ADD_STOCK",
       "NEW_OPERATION",  # Add here
   ]
   ```

2. **Implement in `database.py`**:
   ```python
   def new_operation(data: dict):
       # Your implementation
       return {"status": "ok", ...}
   ```

3. **Add to `write_agent.py`**:
   ```python
   elif operation_type == "NEW_OPERATION":
       result = new_operation(entities)
   ```

4. **Update `router.py`** to recognize keywords for this operation

---

### Add a New Agent

1. Create `agents/new_agent.py`
2. Implement agent function that takes `AgentState` and returns updates
3. Add node to graph in `graph.py`:
   ```python
   workflow.add_node("new_agent", new_agent)
   ```
4. Add routing logic

---

## Key Design Decisions

### Why LangGraph?

- **Explicit State Management**: TypedDict flows through nodes
- **Conditional Routing**: Route based on intent classification
- **Composability**: Easy to add/remove agents
- **Debugging**: Clear execution flow, inspectable state

### Why Separate Agents?

- **Security**: Read agent can't write, write agent can't query
- **Clarity**: Single responsibility per agent
- **Testing**: Each agent can be tested independently
- **Scalability**: Add new agents without breaking existing ones

### Why Resolver Agent?

- **Decoupling**: Write agent doesn't need to know how to resolve "pulseras negras"
- **Reusability**: Both write and read agents can use resolver
- **Flexibility**: Can add complex resolution logic (fuzzy matching, ML, etc.) without changing other agents

---

## Error Handling

Each agent handles errors gracefully:

1. **Router**: If classification fails, returns `AMBIGUOUS`
2. **Resolver**: Flags unresolvable entities as `missing_fields`
3. **Write Agent**: Validates data before execution, returns error if invalid
4. **Read Agent**: Catches SQL errors, returns human-readable message
5. **Final Answer**: Formats errors for user

---

## Testing

### Unit Tests (Recommended)

Test each agent independently:

```python
from agents import create_router_agent

llm = get_llm()
router = create_router_agent(llm)

state = {
    "user_input": "cuántas pulseras tengo",
    "messages": [],
    "normalized_entities": {}
}

result = router(state)
assert result["intent"] == "READ_ANALYTICS"
```

### Integration Tests

Use `example_usage.py` to test the full workflow.

---

## Future Enhancements

1. **Add More Operations**:
   - `register_expense` (full implementation)
   - `update_product`
   - `register_customer`
   - `generate_report`

2. **Add Memory**:
   - Store conversation history
   - Reference previous operations ("like before")

3. **Add Validation Agent**:
   - Pre-validate business rules before write operations
   - Check stock before allowing sale

4. **Add Reporting Agent**:
   - Generate monthly reports
   - Export to PDF/CSV

5. **Multi-language Support**:
   - Better handling of Spanish/English mixing
   - Add more languages

6. **Async Execution**:
   - Run long-running operations in background
   - Stream results to user

---

## Troubleshooting

### "Product not found"

- Check that products exist in database
- Resolver tries exact SKU match first, then partial name match
- Add more products or improve resolver logic

### "Missing required fields"

- Router didn't extract all needed entities
- Improve router prompt with examples
- Add clarification questions

### "Read agent error"

- Check SQL syntax in prompt
- Verify views exist (`stock_current`, `profit_summary`, etc.)
- Run `apply_views.py` to create views

---

## Contact & Support

For issues or questions, refer to the main README or create an issue in the repository.
