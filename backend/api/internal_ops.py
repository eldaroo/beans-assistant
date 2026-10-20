"""Internal operation API for the native-tool-use chat (spec 007, D-036/D-037).

The tools that run on the gateway box hold NO database credentials. They call
these endpoints, gated by the internal service token, which run the real
operation under tenant_context and own every side effect. The tenant is pinned
OUT OF BAND by the gateway (the `x-beans-tenant` header the MCP server sets from
its per-request env), never a model-settable body field; FastAPI re-validates it
here. A model, even a fully hijacked one, cannot choose the tenant and cannot
reach a database connection.

M1 exposes one read, `read_stock`, so the full tool -> internal API -> DB ->
response path is proven. Reads return the module's existing shape. Writes are
two-phase and land in M3+ (D-038): there is no commit capability here.
"""
import logging

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from backend.api.tenant_scope import tenant_scope
from backend.auth.dependencies import _has_internal_token
from backend.services.stock_service import StockService

router = APIRouter()
logger = logging.getLogger(__name__)
stock_service = StockService()

# The gateway's MCP server sets this from its per-request env. It is never a body
# field and never model-settable (D-037).
TENANT_HEADER = "x-beans-tenant"


def _envelope(status_code: int, code: str, message: str) -> JSONResponse:
    """The named-error envelope every internal endpoint returns (genesis-build D)."""
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "error": {"code": code, "message": message}},
    )


def _pinned_tenant(request: Request) -> str:
    return request.headers.get(TENANT_HEADER, "").strip()


@router.post("/internal/ops/read_stock")
async def read_stock(request: Request):
    """Return current stock for the pinned tenant. Internal-token only.

    The body is ignored for scope: the tenant comes only from the pinned header,
    so a `phone` placed in the body by a confused or hostile caller changes
    nothing (D-037).
    """
    if not _has_internal_token(request):
        return _envelope(401, "unauthorized", "internal token required")

    phone = _pinned_tenant(request)
    if not phone:
        return _envelope(400, "tenant_unpinned", "no tenant pinned on the request")

    try:
        with tenant_scope(phone):
            rows = stock_service.get_current_stock(phone=phone, limit=500, offset=0)
        return JSONResponse(content={"ok": True, "stock": jsonable_encoder(rows)})
    except Exception:
        logger.exception("read_stock internal op failed for tenant %s", phone)
        return _envelope(500, "internal_error", "read_stock failed")
