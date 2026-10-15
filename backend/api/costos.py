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
from backend.modules import nav
from backend.services.costing_service import TOTAL_COMPONENTS, CostingService

router = APIRouter()
logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_service = CostingService()


def _usd(cents):
    return None if cents is None else f"{cents / 100:.2f}"


def _comparison_view(product_id):
    """The per-country comparison for one bracelet type (AC9): each of the three
    countries with its landed total, completeness, and margin, and the lowest
    COMPLETE total marked. None when there is no costable type."""
    comp = _service.country_comparison(int(product_id))
    rows = []
    for m in comp.margins:
        rows.append({
            "country": m.country,
            "total": _usd(m.landed.total_cents),
            "is_complete": m.landed.is_complete,
            "pending_labels": m.landed.pending_labels,
            "margin": _usd(m.margin_cents),
            "margin_pending_reason": m.pending_reason,
            "is_lowest_complete": (m.country == comp.lowest_complete_country),
        })
    return {
        "product_name": comp.product_name,
        "lowest_complete_country": comp.lowest_complete_country,
        "rows": rows,
    }


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
        # Per-country comparison for this bracelet type (AC9). Keyed off the same
        # product the breakdown is showing.
        "comparison": _comparison_view(landed.product_id),
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
    business_name = await asyncio.to_thread(nav.business_name, phone)
    response = templates.TemplateResponse(
        request,
        "costos.html",
        {
            "phone": phone,
            "view": view,
            "business_name": business_name,
            "nav": nav.owner_rail(phone),
            "active_route": "costos",
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
