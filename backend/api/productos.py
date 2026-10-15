"""Productos module page: full product ABM (spec 004, S2, T-006).

The exemplar Control Center CRUD page (plan D-025). The three read layers stay
distinct (plan architecture sketch): the home tile is one bounded count
(productos_module), THIS route does the initial page paint (tenant-scoped,
no-store, off the event loop), and the Alpine ``productosDashboard`` factory is
the only write path — it creates via POST, edits via PUT, soft-deletes via
DELETE against the existing /api/tenants/{phone}/products endpoints (reused, not
rewritten) and refetches after each. The page extends cc_base so it wears the
one owner brand with the held rail and Timonel; it never bounces to the legacy
coffee tab.

The route seeds the initial active products into the page as a JSON island so
the first paint shows real rows with no second round-trip; the factory takes it
over for every interaction. Owner-gated by the same ``require_tenant_match``
dependency the status home and the other module pages use.
"""
import asyncio
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.api.tenant_scope import tenant_scope
from backend.auth.dependencies import require_tenant_match
from backend.modules import nav
from backend.services.products_service import ProductsService

router = APIRouter()
logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_service = ProductsService()

# Ceiling on the initial seed, matching the tile's bound. The page paginates /
# searches beyond this; the seed is the first page the owner sees.
SEED_LIMIT = 200


def _row(p) -> dict:
    """Shape one ProductResponse for the JSON seed. Cents stay integers; the
    factory converts to and from the dollar inputs in one place (the money trap:
    the API speaks cents, the form speaks dollars)."""
    return {
        "id": p.id,
        "sku": p.sku,
        "name": p.name,
        "description": p.description or "",
        "unit_cost_cents": p.unit_cost_cents,
        "unit_price_cents": p.unit_price_cents,
        "is_active": bool(p.is_active),
    }


def _build_view(phone: str) -> dict:
    """Initial active-product list for the first paint. The Solo-activos toggle
    refetches with include_inactive client-side; the seed is the active set."""
    products = _service.list_products(
        phone=phone, include_inactive=False, limit=SEED_LIMIT, offset=0
    )
    return {"products": [_row(p) for p in products]}


@router.get("/productos/{phone}", response_class=HTMLResponse)
async def productos_page(
    request: Request,
    phone: str,
    _user: dict = Depends(require_tenant_match),
):
    """Render the Productos ABM page for a tenant."""

    def _work():
        with tenant_scope(phone):
            return _build_view(phone)

    view = await asyncio.to_thread(_work)
    business_name = await asyncio.to_thread(nav.business_name, phone)
    response = templates.TemplateResponse(
        request,
        "productos.html",
        {
            "phone": phone,
            "view": view,
            "business_name": business_name,
            "nav": nav.owner_rail(phone),
            "active_route": "productos",
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
