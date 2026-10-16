"""Resultado module page (spec 004, S5, T-010).

A dedicated Control Center page for the accumulated result, replacing the legacy
?tab=expenses bounce AND fixing the mislabel: the caja/Resultado tile pointed at
the expenses tab, so clicking "Resultado" landed on a gastos form. This page
shows ingresos and ganancia (read from the same AnalyticsService the caja
provider headlines) plus the expenses list, and the tile is repointed to
/resultado/{phone} (AC6).

Three read layers (plan D-025): the home tile is one bounded snapshot
(caja_module, the accumulated net), THIS route paints the initial figures +
expenses (tenant-scoped, no-store, off the event loop), and the Alpine
``resultadoDashboard`` factory is the only write path (expense add via
POST /expenses, delete via DELETE /{id}). Ingresos is paid revenue (server);
gastos and ganancia are derived from the expenses list under ONE definition
(ganancia = ingresos menos gastos), so the three figures stay consistent and
update live when an expense changes. Endpoints reused, not rewritten.
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
from backend.services.analytics_service import AnalyticsService
from backend.services.expenses_service import ExpensesService

router = APIRouter()
logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_analytics = AnalyticsService()
_expenses = ExpensesService()

SEED_LIMIT = 500


def _expense_row(e) -> dict:
    return {
        "id": e.id,
        "expense_date": (e.expense_date or "")[:10],
        "category": e.category,
        "description": e.description,
        "amount_cents": e.amount_cents,
    }


def _build_view(phone: str) -> dict:
    revenue_usd = _analytics.get_revenue(phone).revenue_usd or 0.0
    # The server's lifetime profit (= the same figure the home caja tile shows).
    # When the expenses list is truncated at the seed cap, the page uses THIS as
    # ganancia so the page never overstates the result or disagrees with the tile
    # (council Edut BLOCKER, Winston MED). When not truncated, the client derives
    # ganancia live from the full expenses list.
    profit_usd = _analytics.get_profit(phone).profit_usd or 0.0
    expenses = _expenses.list_expenses(phone=phone, limit=SEED_LIMIT, offset=0)
    return {
        "ingresos_cents": round(revenue_usd * 100),
        "ganancia_server_cents": round(profit_usd * 100),
        "expenses": [_expense_row(e) for e in expenses],
        "truncated": len(expenses) >= SEED_LIMIT,
    }


@router.get("/resultado/{phone}", response_class=HTMLResponse)
async def resultado_page(
    request: Request,
    phone: str,
    _user: dict = Depends(require_tenant_match),
):
    """Render the Resultado page for a tenant."""

    def _work():
        with tenant_scope(phone):
            return _build_view(phone)

    view = await asyncio.to_thread(_work)
    business_name = await asyncio.to_thread(nav.business_name, phone)
    response = templates.TemplateResponse(
        request,
        "resultado.html",
        {
            "phone": phone,
            "view": view,
            "business_name": business_name,
            "nav": nav.owner_rail(phone),
            "active_route": "caja",
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
