"""
FastAPI Backend for Beans&Co Multi-Tenant Business Management System.

Provides REST API endpoints for managing tenants, products, sales, expenses, and analytics.
Includes an admin web interface for easy database management.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import sys
import os
import time
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
    from backend.services.tenants_service import TenantsService

    tenants_service = TenantsService()
    tenant_models = tenants_service.list_tenants(limit=500, offset=0)
    tenants_list = [
        tenant.model_dump() if hasattr(tenant, "model_dump") else tenant.dict()
        for tenant in tenant_models
    ]

    tenants_with_stats = []
    for tenant in tenants_list:
        phone = tenant["phone_number"]

        try:
            stats_model = tenants_service.get_tenant_stats(phone)
            stats = stats_model.model_dump() if hasattr(stats_model, "model_dump") else stats_model.dict()
            stats["products"] = stats["products_count"]
            stats["sales"] = stats["sales_count"]
        except Exception as e:
            print(f"Error getting stats for {phone}: {e}")
            stats = {
                "products_count": 0,
                "sales_count": 0,
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
    from database_config import db as database, tenant_context
    from backend.services.tenants_service import TenantsService, TenantNotFoundError

    tenants_service = TenantsService()
    try:
        tenant = tenants_service.get_tenant(phone)
    except TenantNotFoundError:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": f"Tenant {phone} not found"
            },
            status_code=404
        )

    tenant_phone = tenant.phone_number
    tenant_config = {
        "business_name": tenant.business_name,
        "owner_name": getattr(tenant, "owner_name", None),
        "language": tenant.language,
        "currency": tenant.currency,
    }

    # Get stats from PostgreSQL
    try:
        with tenant_context(tenant_phone):
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
                "products_count": products_count["count"] if products_count else 0,
                "sales_count": sales_count["count"] if sales_count else 0,
                "revenue_usd": revenue_cents / 100.0,
                "profit_usd": profit_usd
            }

            # Backward-compatible keys
            stats["products"] = stats["products_count"]
            stats["sales"] = stats["sales_count"]
    except Exception as e:
        print(f"Error getting stats: {e}")
        stats = {
            "products_count": 0,
            "sales_count": 0,
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
                "phone_number": tenant_phone,
                **tenant_config
            },
            "stats": stats
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint for Consul service monitoring."""
    checks = {}
    overall = "healthy"

    # --- PostgreSQL ---
    use_postgres = os.getenv("USE_POSTGRES", "false").lower() == "true"
    if use_postgres:
        try:
            import psycopg2
            t0 = time.monotonic()
            conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=os.getenv("POSTGRES_PORT", "5432"),
                dbname=os.getenv("POSTGRES_DB", "beansco_main"),
                user=os.getenv("POSTGRES_USER", "beansco"),
                password=os.getenv("POSTGRES_PASSWORD", ""),
                connect_timeout=3,
            )
            conn.cursor().execute("SELECT 1")
            conn.close()
            checks["database"] = {"status": "healthy", "latency_ms": round((time.monotonic() - t0) * 1000)}
        except Exception as e:
            checks["database"] = {"status": "unhealthy", "error": str(e)}
            overall = "unhealthy"
    else:
        checks["database"] = {"status": "healthy", "engine": "sqlite"}

    # --- Redis ---
    redis_enabled = os.getenv("REDIS_ENABLED", "false").lower() == "true"
    if redis_enabled:
        try:
            t0 = time.monotonic()
            client = cache.get_redis_client()
            if client:
                client.ping()
                checks["redis"] = {"status": "healthy", "latency_ms": round((time.monotonic() - t0) * 1000)}
            else:
                checks["redis"] = {"status": "unhealthy", "error": "client unavailable"}
                if overall == "healthy":
                    overall = "degraded"
        except Exception as e:
            checks["redis"] = {"status": "unhealthy", "error": str(e)}
            if overall == "healthy":
                overall = "degraded"
    else:
        checks["redis"] = {"status": "disabled"}

    # --- Google Gemini API key ---
    google_key = os.getenv("GOOGLE_API_KEY", "")
    checks["gemini_api"] = {"status": "healthy" if google_key else "unhealthy", "configured": bool(google_key)}
    if not google_key:
        overall = "unhealthy"

    # --- WhatsApp (Baileys) ---
    whatsapp_url = os.getenv("WHATSAPP_URL", "http://whatsapp:3000")
    try:
        import urllib.request
        t0 = time.monotonic()
        with urllib.request.urlopen(f"{whatsapp_url}/health", timeout=3) as resp:
            import json as _json
            wa_data = _json.loads(resp.read())
            checks["whatsapp"] = {"status": wa_data.get("status", "unknown"), "whatsapp": wa_data.get("whatsapp"), "latency_ms": round((time.monotonic() - t0) * 1000)}
    except Exception as e:
        checks["whatsapp"] = {"status": "unhealthy", "error": str(e)}
        if overall == "healthy":
            overall = "degraded"

    status_code = 200 if overall in ("healthy", "degraded") else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "service": "Beans&Co Multi-Tenant API",
            "checks": checks,
        },
    )


@app.get("/test-products")
async def test_products():
    """Test endpoint to debug products issue."""
    import sys
    sys.path.append(str(Path(__file__).parent.parent))
    import database
    token = database.set_tenant_db_path("data/clients/+541153695627/business.db")

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
    finally:
        database.reset_tenant_db_path(token)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
