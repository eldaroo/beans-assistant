# Beans&Co Business Assistant 🫘

Multi-tenant WhatsApp business assistant with AI-powered analytics and operations.

## Features

### 🤖 Multi-Agent System
- **Router Agent**: Intent classification (READ_ANALYTICS, WRITE_OPERATION, MIXED)
- **Resolver Agent**: Hybrid product resolution (deterministic + LLM fallback)
- **Write Agent**: Business operations (sales, expenses, inventory, products)
- **Read Agent**: Analytics queries with Chain-of-Thought reasoning

### 🏢 Multi-Tenant Support
- Isolated databases per client
- Custom configuration per tenant
- Support for multiple currencies (USD, AUD, etc.)
- Localized prompts (English, Spanish)

### 📊 Business Operations
- **Sales**: Register sales with automatic stock deduction
- **Inventory**: Add/remove stock, track movements
- **Products**: Create products with dynamic SKU generation
- **Expenses**: Track business expenses
- **Analytics**: Revenue, profit, stock queries

### 🔧 Key Features
- **Dynamic SKU Generation**: Handles ANY product name without hardcoded mappings
- **Hybrid Resolver**: 90%+ deterministic matching, <10% LLM for ambiguous cases
- **Product Deactivation**: Soft delete preserves historical data
- **Active Product Filtering**: Stock queries only show active products

## Setup

### Prerequisites
- Python 3.10+
- SQLite3
- Google API Key (for Gemini LLM)

### Installation
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Add GOOGLE_API_KEY to .env
```

### Running the Servers

**Quick Start** - Start both WhatsApp and Backend servers:
```bash
./start_server.sh
```

This will start:
- **WhatsApp Server**: Multi-tenant business assistant
- **Backend API**: REST API + Admin UI at http://localhost:8000

**Check Status**:
```bash
./check_server.sh
```

**Stop Servers**:
```bash
./stop_server.sh
```

### Running Tests
```bash
# Run all tests
pytest

# Run specific test suite
pytest tests/unit/test_database.py
pytest tests/unit/test_resolver.py
pytest tests/unit/test_write_agent.py

# Run with coverage
pytest --cov=. --cov-report=html
```

## Multi-Tenant Setup

### Add New Tenant
```bash
# Example: Australia tenant
python setup_beans_australia.py
```

### Tenant Structure
```
data/clients/+61476777212/
├── business.db        # Isolated database
└── config.json        # Tenant configuration

configs/
└── tenant_registry.json  # All tenants registry
```

## Recent Updates (Jan 2025)

### ✅ Backend Admin Panel (NEW!)
- **Interactive Dashboard**: Full CRUD operations with real-time updates
- **Data Tables**: Products, Stock, Sales, Expenses with live refresh
- **Inline Editing**: Edit stock quantities directly in table rows (NEW!)
- **Bulk Operations**: Multi-select and bulk delete functionality
- **Modals**: Add/Edit forms with validation
- **Auto-refresh**: Data updates every 30 seconds
- **Modern UI**: Built with Tailwind CSS + Alpine.js
- **Keyboard Shortcuts**: Enter to save, Escape to cancel

### ✅ Product Management
- Added `DEACTIVATE_PRODUCT` operation
- Fixed stock queries to filter inactive products
- Updated `stock_current` view with `WHERE is_active = 1`

### ✅ Testing
- 111 comprehensive tests passing
- Unit tests for database, resolver, write agent
- Integration tests for hybrid resolver
- CI/CD with GitHub Actions

### ✅ Multi-Tenant
- Added Beans&Co Australia (+61476777212)
- English/AUD configuration
- Timezone: Australia/Sydney

## Architecture

See [README_MULTI_AGENT.md](README_MULTI_AGENT.md) for detailed architecture documentation.

## License

Proprietary - Beans&Co
