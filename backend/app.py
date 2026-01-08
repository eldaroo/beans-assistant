"""
FastAPI Backend for Beans&Co Multi-Tenant Business Management System.

Provides REST API endpoints for managing tenants, products, sales, expenses, and analytics.
Includes an admin web interface for easy database management.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Import API routers
from backend.api import tenants, products, sales, expenses, stock, analytics, chat, chat_tenant
from backend import cache

# Initialize FastAPI app
app = FastAPI(
    title="Beans&Co Multi-Tenant API",
    description="REST API for managing multi-tenant business data",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware - allow all origins (no auth for now)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get absolute paths
BACKEND_DIR = Path(__file__).parent
STATIC_DIR = BACKEND_DIR / "static"
TEMPLATES_DIR = BACKEND_DIR / "templates"

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Include API routers
app.include_router(tenants.router, prefix="/api/tenants", tags=["Tenants"])
app.include_router(products.router, prefix="/api/tenants", tags=["Products"])
app.include_router(sales.router, prefix="/api/tenants", tags=["Sales"])
app.include_router(expenses.router, prefix="/api/tenants", tags=["Expenses"])
app.include_router(stock.router, prefix="/api/tenants", tags=["Stock"])
app.include_router(analytics.router, prefix="/api/tenants", tags=["Analytics"])
app.include_router(chat.router, prefix="/api", tags=["Chat Simulation"])
app.include_router(chat_tenant.router, prefix="/api/tenants", tags=["Tenant Chat"])



# HTML Routes (Admin UI)
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - list of all tenants."""
    from database_config import db as database
    import json

    # Load tenant registry (if exists) for tenant metadata
    registry_path = Path("configs/tenant_registry.json")
    tenants_list = []

    if registry_path.exists():
        with open(registry_path, 'r', encoding='utf-8') as f:
            registry = json.load(f)
            tenants_list = [
                {
                    "phone_number": phone,
                    **data
                }
                for phone, data in registry.items()
            ]

    # Get stats for each tenant from PostgreSQL
    tenants_with_stats = []
    for tenant in tenants_list:
        phone = tenant["phone_number"]

        # Get stats from PostgreSQL (with caching)
        try:
            # Try to get from cache
            stats = cache.get_cached_stats(phone)
            if stats is None:
                # Cache miss - query database
                # Product count
                products_count = database.fetch_one("SELECT COUNT(*) as count FROM products")

                # Sales count
                sales_count = database.fetch_one("SELECT COUNT(*) as count FROM sales")

                # Revenue
                revenue = database.fetch_one("SELECT total_revenue_cents FROM revenue_paid")
                revenue_cents = revenue["total_revenue_cents"] if revenue and revenue["total_revenue_cents"] else 0

                # Profit
                profit = database.fetch_one("SELECT profit_usd FROM profit_summary")
                profit_usd = profit["profit_usd"] if profit and profit["profit_usd"] else 0.0

                stats = {
                    "products": products_count["count"] if products_count else 0,
                    "sales": sales_count["count"] if sales_count else 0,
                    "revenue_usd": revenue_cents / 100.0,
                    "profit_usd": profit_usd
                }
                
                # Cache the stats
                cache.cache_stats(phone, stats)
        except Exception as e:
            print(f"Error getting stats for {phone}: {e}")
            stats = {
                "products": 0,
                "sales": 0,
                "revenue_usd": 0.0,
                "profit_usd": 0.0
            }

        tenants_with_stats.append({
            **tenant,
            "stats": stats
        })

    return templates.TemplateResponse(
        "tenants.html",
        {
            "request": request,
            "tenants": tenants_with_stats
        }
    )


@app.get("/tenants/{phone}", response_class=HTMLResponse)
async def tenant_detail(request: Request, phone: str):
    """Tenant detail page - dashboard with tabs."""
    from database_config import db as database
    import json

    # Load tenant config from registry
    registry_path = Path("configs/tenant_registry.json")
    tenant_config = {
        "business_name": "Unknown",
        "language": "es",
        "currency": "USD"
    }

    if registry_path.exists():
        with open(registry_path, 'r', encoding='utf-8') as f:
            registry = json.load(f)
            if phone in registry:
                tenant_config["business_name"] = registry[phone].get("business_name", "Unknown")
            else:
                return templates.TemplateResponse(
                    "error.html",
                    {
                        "request": request,
                        "error": f"Tenant {phone} not found"
                    },
                    status_code=404
                )

    # Get stats from PostgreSQL
    try:
        # Product count
        products_count = database.fetch_one("SELECT COUNT(*) as count FROM products")

        # Sales count
        sales_count = database.fetch_one("SELECT COUNT(*) as count FROM sales")

        # Revenue
        revenue = database.fetch_one("SELECT total_revenue_cents FROM revenue_paid")
        revenue_cents = revenue["total_revenue_cents"] if revenue and revenue["total_revenue_cents"] else 0

        # Profit
        profit = database.fetch_one("SELECT profit_usd FROM profit_summary")
        profit_usd = profit["profit_usd"] if profit and profit["profit_usd"] else 0.0

        stats = {
            "products": products_count["count"] if products_count else 0,
            "sales": sales_count["count"] if sales_count else 0,
            "revenue_usd": revenue_cents / 100.0,
            "profit_usd": profit_usd
        }
    except Exception as e:
        print(f"Error getting stats: {e}")
        stats = {
            "products": 0,
            "sales": 0,
            "revenue_usd": 0.0,
            "profit_usd": 0.0
        }

    return templates.TemplateResponse(
        "tenant_detail.html",
        {
            "request": request,
            "tenant": {
                "phone_number": phone,
                **tenant_config
            },
            "stats": stats
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Beans&Co Multi-Tenant API"
    }


@app.get("/test-products")
async def test_products():
    """Test endpoint to debug products issue."""
    import sys
    sys.path.append(str(Path(__file__).parent.parent))
    import database
    database.DB_PATH = "data/clients/+541153695627/business.db"

    try:
        rows = database.fetch_all("SELECT * FROM products LIMIT 1")
        if rows:
            row_dict = dict(rows[0])
            return {"status": "ok", "sample_product": row_dict}
        return {"status": "ok", "message": "No products found"}
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
