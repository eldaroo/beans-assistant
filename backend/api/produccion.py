"""Produccion module drill-down (spec 003 M3).

Renders units produced this week against the target, per country, plus any
overdue arrival (the frozen mockup's uniform module page). Owner-gated by the
same ``require_tenant_match`` dependency the status home uses.

The read runs off the event loop and inside the tenant scope, mirroring the home
and costos routes.
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
from backend.services.production_service import ProductionService

router = APIRouter()
logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_service = ProductionService()


def _row(status):
    return {
        "country": status.country,
        "period_week": status.period_week,
        "units_produced": status.units_produced,
        "units_target": status.units_target,
        "has_target": status.has_target,
        "pct": status.pct_of_target,
        "meets_target": status.meets_target,
        "expected_next_at": status.expected_next_at,
        "is_overdue": status.is_overdue,
    }


def _build_view():
    """Shape the per-country production for the template. Returns None when the
    tenant has no production recorded yet."""
    rows = [_row(s) for s in _service.per_country() if s]
    if not rows:
        return None
    return {
        "rows": rows,
        "overdue_count": sum(1 for r in rows if r["is_overdue"]),
    }


@router.get("/produccion/{phone}", response_class=HTMLResponse)
async def produccion_page(
    request: Request,
    phone: str,
    _user: dict = Depends(require_tenant_match),
):
    """Render the Produccion drill-down for a tenant."""

    def _work():
        with tenant_scope(phone):
            return _build_view()

    view = await asyncio.to_thread(_work)
    business_name = await asyncio.to_thread(nav.business_name, phone)
    response = templates.TemplateResponse(
        request,
        "produccion.html",
        {
            "phone": phone,
            "view": view,
            "business_name": business_name,
            "nav": nav.owner_rail(phone),
            "active_route": "produccion",
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
