"""Status-home route: the Control Center default landing (AC2).

Renders one tile per registered module plus the attention strip, driven entirely
by the module registry. Adding a module to ``backend/modules/registry.py`` adds
a tile and rail entry with no edit here (AC1). The route is tenant-scoped and
owner-gated by the same ``require_tenant_match`` dependency the rest of the
owner surface uses; the supplier two-rooms split arrives in M6.

The view is built off the event loop (``asyncio.to_thread``) and each module's
snapshot is bounded by a timeout in the home service, so one slow or broken
module cannot stall this request or the worker (AC3).
"""
import asyncio
import logging
from pathlib import Path
import sys

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.auth.dependencies import require_tenant_match
from backend.modules import daily_truth, home_service, nav

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_daily_truth(phone: str, view: "home_service.HomeView") -> str:
    """Compose the Hoy daily-truth headline (spec 006 T-010 / AC3).

    Reads today's paid/unpaid sale counts with one cheap aggregate and pairs
    them with the top attention item already computed for the strip. Fail-open:
    if the today-counts read raises (DB blip), the headline still renders from
    the attention strip alone (counts treated as zero) rather than 500-ing the
    home — the same degrade philosophy build_home uses for a slow module.
    """
    from backend.api.tenant_scope import tenant_scope
    from backend.services.analytics_service import AnalyticsService

    # Whole compose is guarded (not just the DB read): reading view.attention and
    # composing the sentence are cheap and pure today, but keeping them inside the
    # guard means a future view-shape change can never 500 the home — the headline
    # degrades to the empty-day sentence rather than taking the page down (AC3 says
    # the headline must be present, never that it may crash the home).
    try:
        top_attention = view.attention[0].text if view.attention else None
        with tenant_scope(phone):
            paid_today, unpaid_today = AnalyticsService().get_today_sales_counts(phone)
        return daily_truth.daily_truth_headline(paid_today, unpaid_today, top_attention)
    except Exception:
        logger.exception("daily-truth headline build failed for %s; using empty-day sentence", phone)
        return daily_truth.EMPTY_DAY

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
# Forward-compatible signature: pass the request first (Starlette >= 0.29).
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _resolve_business_name(phone: str) -> str:
    """Resolve the tenant and return its business name.

    Raises 404 for a genuinely nonexistent tenant (so an admin or internal-token
    caller hitting /home/{unknown} gets a 404, not a welcome page). A transient
    lookup failure (DB down) does NOT 404; the page still renders with degraded
    tiles so the outage is visible.
    """
    from backend.services.tenants_service import TenantsService, TenantNotFoundError

    try:
        tenant = TenantsService().get_tenant(phone)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant {phone} not found") from exc
    except Exception:
        logger.exception("tenant lookup failed for %s; rendering home best-effort", phone)
        return "Beans&Co"
    return getattr(tenant, "business_name", None) or "Beans&Co"


@router.get("/home/{phone}", response_class=HTMLResponse)
async def status_home(request: Request, phone: str, _user: dict = Depends(require_tenant_match)):
    """Render the status home for a tenant."""
    business_name = _resolve_business_name(phone)
    view = await asyncio.to_thread(home_service.build_home, phone)
    # Hoy daily-truth headline (spec 006 T-010): one plain-Spanish sentence from
    # today's sale counts + the top attention item, built off the event loop.
    daily_truth_line = await asyncio.to_thread(_build_daily_truth, phone, view)
    # Three-tab shell (spec 006): the tabs come from the registry groups, the
    # per-tab tiles are grouped from the SINGLE build_home fan-out above (AC6, no
    # new query per tab).
    tabs = nav.owner_tabs()
    tab_tiles = home_service.tiles_by_tab(view, tabs)
    # The active tab is server-selected from ?tab= so each tab is reachable and
    # deep-linkable with JS off (the client router then switches with no reload);
    # an unknown or absent tab lands on Hoy.
    requested_tab = request.query_params.get("tab")
    active_tab = requested_tab if requested_tab in {t.id for t in tabs} else nav.HOY_ID
    response = templates.TemplateResponse(
        request,
        "control_center.html",
        {
            "phone": phone,
            "business_name": business_name,
            "view": view,
            "tabs": tabs,
            "tab_tiles": tab_tiles,
            "active_tab": active_tab,
            "active_route": "home",
            "daily_truth": daily_truth_line,
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
