"""Ventas module page (spec 004, S4, T-008 + T-009).

A dedicated Control Center page for sales, replacing the legacy ?tab=sales
bounce. Same three-read-layer shape as the Productos/Stock pages (plan D-025):
the home tile is one bounded snapshot (ventas_module), THIS route paints the
initial sales list (tenant-scoped, no-store, off the event loop), and the Alpine
``ventasDashboard`` factory is the only write path. It lists sales, cancels via
DELETE /api/tenants/{phone}/sales/{id}, opens a detail modal from
GET /sales/{id} (not the legacy ``alert`` stub), and records a new sale through a
line-item modal via POST /sales (built, not ported — T-009, A-Q12: against the
existing SaleCreate contract, any gap is a separate task). Endpoints reused, not
rewritten.

The page extends cc_base so it wears the one owner brand and never bounces to the
legacy coffee tab; the Ventas tile is repointed to /ventas/{phone} in the
registry (AC5). Owner-gated by require_tenant_match like every module page. The
route seeds the active products too, so the record-sale modal has its product
picker on first open with no extra round-trip.
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
from backend.services.sales_service import SalesService

router = APIRouter()
logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_sales = SalesService()
_products = ProductsService()

SEED_LIMIT = 50
PRODUCT_LIMIT = 200


def _sale_row(s) -> dict:
    return {
        "id": s.id,
        "sale_number": s.sale_number,
        "status": s.status,
        "total_amount_cents": s.total_amount_cents,
        "customer_name": s.customer_name or "",
        "created_at": (s.created_at or "")[:10],
        "items": [
            {
                "product_name": getattr(it, "product_name", None) or "producto",
                "product_sku": getattr(it, "product_sku", None) or "",
                "quantity": it.quantity,
                "unit_price_cents": it.unit_price_cents,
                "line_total_cents": it.line_total_cents,
            }
            for it in (s.items or [])
        ],
    }


def _product_row(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "sku": p.sku,
        "unit_price_cents": p.unit_price_cents,
    }


def _build_view(phone: str) -> dict:
    sales = _sales.list_sales(phone=phone, limit=SEED_LIMIT, offset=0)
    products = _products.list_products(
        phone=phone, include_inactive=False, limit=PRODUCT_LIMIT, offset=0
    )
    return {
        "sales": [_sale_row(s) for s in sales],
        "products": [_product_row(p) for p in products],
    }


@router.get("/ventas/{phone}", response_class=HTMLResponse)
async def ventas_page(
    request: Request,
    phone: str,
    _user: dict = Depends(require_tenant_match),
):
    """Render the Ventas page for a tenant."""

    def _work():
        with tenant_scope(phone):
            return _build_view(phone)

    view = await asyncio.to_thread(_work)
    business_name = await asyncio.to_thread(nav.business_name, phone)
    response = templates.TemplateResponse(
        request,
        "ventas.html",
        {
            "phone": phone,
            "view": view,
            "business_name": business_name,
            "tabs": nav.owner_tabs(),
            "active_tab": nav.tab_id_for_module("ventas"),
            "active_route": "ventas",
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
