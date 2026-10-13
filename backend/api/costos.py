"""Costos module drill-down (spec 003 M2).

Renders the landed cost per bracelet type per country as a component breakdown
with a completeness badge (the frozen mockup's Costos section). Owner-gated by
the same ``require_tenant_match`` dependency the status home uses; the supplier
two-rooms split (a supplier never sees a cost or margin, D-017) arrives in M6.

The compute runs off the event loop and inside the tenant scope, mirroring the
home route. ``?product=<id>&country=<name>`` picks a specific type/country;
without them the lead bracelet type and its first country are shown.
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
from backend.services.costing_service import TOTAL_COMPONENTS, CostingService

router = APIRouter()
logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_service = CostingService()


def _build_view(product, country):
    """Compute the landed cost (lead type by default) and shape it for the
    template. Returns None when the tenant has no costing data yet."""
    if product is not None and country:
        landed = _service.landed_cost(int(product), country)
    else:
        landed = _service.lead_landed_cost()
    if landed is None:
        return None
    rows = [
        {
            "label": c.label,
            "detail": c.detail,
            "filled": c.is_filled,
            "value": (f"{c.cents / 100:.2f}" if c.is_filled else None),
        }
        for c in landed.components
    ]
    return {
        "product_name": landed.product_name,
        "country": landed.country,
        "rows": rows,
        "total": f"{landed.total_cents / 100:.2f}",
        "is_complete": landed.is_complete,
        "filled_count": landed.filled_count,
        "total_components": TOTAL_COMPONENTS,
        "pending_labels": landed.pending_labels,
    }


@router.get("/costos/{phone}", response_class=HTMLResponse)
async def costos_page(
    request: Request,
    phone: str,
    product: int | None = None,
    country: str | None = None,
    _user: dict = Depends(require_tenant_match),
):
    """Render the Costos drill-down for a tenant."""

    def _work():
        with tenant_scope(phone):
            return _build_view(product, country)

    view = await asyncio.to_thread(_work)
    response = templates.TemplateResponse(
        request,
        "costos.html",
        {"phone": phone, "view": view},
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
