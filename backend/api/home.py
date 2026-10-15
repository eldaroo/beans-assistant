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
from backend.modules import home_service

router = APIRouter()
logger = logging.getLogger(__name__)

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
    response = templates.TemplateResponse(
        request,
        "control_center.html",
        {
            "phone": phone,
            "business_name": business_name,
            "view": view,
            # cc_base renders the held rail from `nav`; the home passes its own
            # rail_groups so the shell is byte-identical to the pre-rebase home.
            "nav": view.rail_groups,
            "active_route": "home",
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
