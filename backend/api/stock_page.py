"""Stock module page (spec 004, S3, T-007).

A dedicated Control Center page for inventory, replacing the legacy ?tab=stock
bounce. Same three-read-layer shape as the Productos page (plan D-025): the home
tile is one bounded count (stock_module), THIS route paints the initial stock
list (tenant-scoped, no-store, off the event loop), and the Alpine
``stockDashboard`` factory is the only write path — it adds units via
POST /api/tenants/{phone}/stock/add and adjusts an existing quantity via
POST /stock/adjust with the SIGNED delta ``newQty - currentQty`` (the signed-
delta trap: the cell shows an absolute quantity, the endpoint takes a delta).
Endpoints reused, not rewritten.

The page extends cc_base so it wears the one owner brand and never bounces to
the legacy coffee tab; the Stock tile route is repointed to /stock/{phone} in
the registry (T-007 / AC4). Owner-gated by require_tenant_match like every
module page.
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
from backend.modules.providers.stock_module import LOW_STOCK_THRESHOLD
from backend.services.stock_service import StockService

router = APIRouter()
logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_service = StockService()

SEED_LIMIT = 200


def _row(s) -> dict:
    return {
        "product_id": s.product_id,
        "sku": s.sku,
        "name": s.name,
        "stock_qty": int(s.stock_qty or 0),
    }


def _build_view(phone: str) -> dict:
    items = _service.get_current_stock(phone=phone, limit=SEED_LIMIT, offset=0)
    return {
        "stock": [_row(s) for s in items],
        "low_stock_threshold": LOW_STOCK_THRESHOLD,
    }


@router.get("/stock/{phone}", response_class=HTMLResponse)
async def stock_page(
    request: Request,
    phone: str,
    _user: dict = Depends(require_tenant_match),
):
    """Render the Stock page for a tenant."""

    def _work():
        with tenant_scope(phone):
            return _build_view(phone)

    view = await asyncio.to_thread(_work)
    business_name = await asyncio.to_thread(nav.business_name, phone)
    response = templates.TemplateResponse(
        request,
        "stock.html",
        {
            "phone": phone,
            "view": view,
            "business_name": business_name,
            "tabs": nav.owner_tabs(),
            "active_tab": nav.tab_id_for_module("stock"),
            "active_route": "stock",
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
