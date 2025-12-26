# Quick Start Guide - Beans&Co Multi-Agent System

Get started with the multi-agent business system in 5 minutes.

## Prerequisites

- Python 3.10 or higher
- Google API Key (for Gemini)

## Installation

### 1. Clone or Download the Project

```bash
cd supabase-sql-agent
```

### 2. Create Virtual Environment (Recommended)

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/Mac
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Create a `.env` file:

```bash
# Copy example
cp .env.example .env

# Edit .env and add your API key
GOOGLE_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.0-flash-exp
```

Get your Google API key from: https://makersuite.google.com/app/apikey

### 5. Initialize Database

```bash
# Create database and tables
python init_db.py

# Create business views
python apply_views.py
```

### 6. Verify Setup

```bash
python verify_setup.py
```

You should see all checks passing with ✓.

## Usage

### Interactive Mode (Recommended for First Time)

```bash
python graph.py
```

Try these commands:

```
You> cuántas pulseras tengo de cada tipo?
You> registrame una venta de 2 pulseras negras
You> gasté 30 dólares en marketing ayer
You> vendí 1 pulsera gold, cómo queda el stock?
You> exit
```

### Single Query Mode

```bash
python graph.py -q "what's my total revenue?"
```

### Run Examples

```bash
# Run all examples
python example_usage.py

# Run specific examples
python example_usage.py read     # Analytical queries
python example_usage.py write    # Write operations
python example_usage.py mixed    # Mixed operations
python example_usage.py full     # Full verbose flow
```

## Example Queries

### Analytics (READ_ANALYTICS)

These queries retrieve data without modifying anything:

```
¿cuántas pulseras tengo de cada tipo?
what's my total revenue?
show me current profit
cuánto stock tengo en total
how many products do I have?
```

### Operations (WRITE_OPERATION)

These modify the database:

```
registrame una venta de 5 pulseras classic
I sold 3 black bracelets
gasté 50 dólares en marketing ayer
add 100 units to black bracelets
crear producto BC-TEST con precio 20 dólares
```

### Mixed (Write + Read)

These do an operation and then check the result:

```
vendí 2 pulseras black, ¿cómo queda el stock?
register a sale of 1 gold bracelet and show me revenue
gasté 100 dólares, cuál es el profit ahora?
```

## Understanding the Output

When you run a query, you'll see the execution flow:

```
============================================================
EXECUTION FLOW:
============================================================

[ROUTER]
Intent classified as WRITE_OPERATION. Reasoning: User says 'vendí'

[RESOLVER]
Resolved entities: 3 fields

[WRITE_AGENT]
Registering sale of 1 item type(s) with status PAID...
✓ Sale registered (ID: 6, Total: $28.00)
  Current revenue: $1100.00
  Current profit: $850.00

============================================================

✓ Sale registered (ID: 6, Total: $28.00)
  Current revenue: $1100.00
  Current profit: $850.00
```

## Architecture Overview

The system uses 4 specialized agents:

```
User Input
    ↓
Router Agent (classifies intent)
    ↓
    ├─→ Read Agent (SQL only) ─→ Answer
    │
    └─→ Resolver → Write Agent → (Read Agent) → Answer
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for details.

## Troubleshooting

### "No API key found"

Set `GOOGLE_API_KEY` in your `.env` file.

### "Product not found"

The database needs products. Check products with:

```bash
python graph.py -q "show me all products"
```

### "View does not exist"

Run the view creation script:

```bash
python apply_views.py
```

### Import errors

Install dependencies:

```bash
pip install -r requirements.txt
```

## Next Steps

1. **Explore Examples**: Run `python example_usage.py` to see various use cases
2. **Read Architecture**: Check [ARCHITECTURE.md](ARCHITECTURE.md) for deep dive
3. **Extend System**: See [README_MULTI_AGENT.md](README_MULTI_AGENT.md) for adding features
4. **View Flow**: Open [FLOW_DIAGRAM.txt](FLOW_DIAGRAM.txt) for visual workflow

## Common Tasks

### Add a New Product

```
You> crear producto BC-RING-SILVER con nombre 'Coffee Ring Silver' precio 25 dólares costo 10 dólares
```

### Register a Sale

```
You> registrame una venta de 3 pulseras black
```

### Add Stock

```
You> agregar 50 unidades de pulseras classic
```

### Register an Expense

```
You> gasté 100 dólares en materiales ayer
```

### Check Analytics

```
You> cuánto profit tengo?
You> cuál es mi revenue total?
You> cuánto stock tengo de cada producto?
```

## Support

- **Documentation**: See [ARCHITECTURE.md](ARCHITECTURE.md)
- **Examples**: Run `python example_usage.py`
- **Verification**: Run `python verify_setup.py`

## Development Mode

To modify the system:

1. Edit agents in `agents/` directory
2. Modify graph workflow in `graph.py`
3. Add business functions in `database.py`
4. Test with `verify_setup.py`

Happy coding! 🚀
