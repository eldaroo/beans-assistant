"""Logistica module drill-down (spec 003 M4, T-016).

Renders the lead bracelet type's shipping and customs per country with a
pending badge where a line is not yet known (the pending-customs signal made
visible). Owner-gated by the same ``require_tenant_match`` dependency the status
home and Costos page use; the supplier two-rooms split arrives in M6. The compute
runs off the event loop inside the tenant scope, mirroring the home and Costos routes.
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
from backend.services.logistics_service import LogisticsService

router = APIRouter()
logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_service = LogisticsService()


def _usd(cents):
    return None if cents is None else f"{cents / 100:.2f}"


def _build_view():
    """The lead type's logistics lanes shaped for the template. None when the
    tenant has no costable bracelet type yet."""
    lanes = _service.lead_lanes()
    if lanes is None:
        return None
    types = _service.repository.list_bracelet_types()
    rows = []
    for ln in lanes:
        rows.append({
            "country": ln.country,
            "shipping": _usd(ln.shipping_cents),
            "customs": _usd(ln.customs_cents),
            "total": _usd(ln.total_cents),
            "is_complete": ln.is_complete,
            "customs_pending": ln.customs_pending,
            "pending_labels": ln.pending_labels,
        })
    complete = [ln for ln in lanes if ln.is_complete]
    cheapest = min(complete, key=lambda ln: ln.total_cents).country if complete else None
    return {
        "product_name": (types[0]["name"] if types else ""),
        "rows": rows,
        "cheapest_country": cheapest,
    }


@router.get("/logistica/{phone}", response_class=HTMLResponse)
async def logistica_page(
    request: Request,
    phone: str,
    _user: dict = Depends(require_tenant_match),
):
    """Render the Logistica drill-down for a tenant."""

    def _work():
        with tenant_scope(phone):
            return _build_view()

    view = await asyncio.to_thread(_work)
    business_name = await asyncio.to_thread(nav.business_name, phone)
    response = templates.TemplateResponse(
        request,
        "logistica.html",
        {
            "phone": phone,
            "view": view,
            "business_name": business_name,
            "nav": nav.owner_rail(phone),
            "active_route": "logistica",
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
