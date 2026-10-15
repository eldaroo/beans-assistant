"""Proveedores module drill-down (spec 003 M5, T-017/T-018).

Renders the active supplier directory with each supplier's check-in status and an
overdue badge where the last check-in is older than the window (the signal made
visible). Owner-gated by the same ``require_tenant_match`` dependency the status
home and the other module pages use; the supplier two-rooms self-service view is
M6. The read runs off the event loop inside the tenant scope. No margins, prices,
or costs render here (D-017 two-rooms rule begins at this surface).
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
from backend.services.supplier_service import SupplierService

router = APIRouter()
logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_service = SupplierService()


def _build_view():
    """The active supplier directory shaped for the template. Always a dict (an
    empty directory renders the empty state), never None."""
    directory = _service.directory()
    rows = [
        {
            "name": s.name,
            "country": s.country,
            "contact": s.contact,
            "last_checkin_at": s.last_checkin_at,
            "days_since_checkin": s.days_since_checkin,
            "is_overdue": s.is_overdue,
        }
        for s in directory
    ]
    return {
        "count": len(rows),
        "overdue_count": sum(1 for r in rows if r["is_overdue"]),
        "window_days": _service.window_days,
        "rows": rows,
    }


@router.get("/proveedores/{phone}", response_class=HTMLResponse)
async def proveedores_page(
    request: Request,
    phone: str,
    _user: dict = Depends(require_tenant_match),
):
    """Render the Proveedores drill-down for a tenant."""

    def _work():
        with tenant_scope(phone):
            return _build_view()

    view = await asyncio.to_thread(_work)
    business_name = await asyncio.to_thread(nav.business_name, phone)
    response = templates.TemplateResponse(
        request,
        "proveedores.html",
        {
            "phone": phone,
            "view": view,
            "business_name": business_name,
            "nav": nav.owner_rail(phone),
            "active_route": "proveedores",
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
