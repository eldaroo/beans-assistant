"""Internal operation API for the native-tool-use chat (spec 007, D-036/D-037).

The tools that run on the gateway box hold NO database credentials. They call
these endpoints, gated by the internal service token, which run the real
operation under tenant_context and own every side effect. The tenant is pinned
OUT OF BAND by the gateway (the `x-beans-tenant` header the MCP server sets from
its per-request env), never a model-settable body field; FastAPI re-validates it
here. A model, even a fully hijacked one, cannot choose the tenant and cannot
reach a database connection.

M1 exposed one read, `read_stock`, to prove the full tool -> internal API -> DB ->
response path. M2 adds the rest of the read surface (s-04): revenue, profit, a
day-by-day sales summary, the eight command-center module snapshots, and a
`business_status` read that returns the ONE existing attention aggregation
(`home_service.build_home().attention`, which is `attention_service.aggregate()`
plus `prioritize()`), never a second opinion (AC6). Reads return the module's
existing shape. Writes are two-phase and land in M3+ (D-038): there is still no
commit capability here.

Endpoints are intentionally SYNCHRONOUS `def` (not `async def`): the chat path
drives a blocking outbound agent call, and an async internal endpoint on the same
event loop reintroduced the agent-callback deadlock (M1 fix ca1a7c1). FastAPI runs
sync endpoints in a threadpool, so a blocking read here never starves the loop.
Body models are declared as optional `Body(...)` params so FastAPI re-validates the
non-tenant arguments with Pydantic (AC4) while an empty body `{}` still resolves to
defaults.
"""
import logging
import uuid

from fastapi import APIRouter, Body, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.api.tenant_scope import tenant_scope
from backend.auth.dependencies import _has_internal_token
from backend.modules import registry
from backend.modules.home_service import build_home
from backend.repositories import pending_ops_repository as pending_ops
from backend.services import ops_guard, ops_resolver
from backend.services.analytics_service import AnalyticsService
from backend.services.stock_service import StockService
from database_config import fetch_one, get_last_operation

router = APIRouter()
logger = logging.getLogger(__name__)
stock_service = StockService()
analytics_service = AnalyticsService()

# The gateway's MCP server sets these from its per-request env. Neither is a body field
# and neither is model-settable (D-037). The turn nonce identifies the agent turn that
# staged a write, so the app correlates a staged op to the operator's utterance by identity.
TENANT_HEADER = "x-beans-tenant"
TURN_HEADER = "x-beans-turn"

# The eight command-center module ids read_module accepts. Mirrors the MCP tool's
# closed enum (deploy/beans-mcp.mjs MODULE_IDS) and the registry; a module id outside
# this set is a named 400, never an arbitrary or empty read.
MODULE_IDS = {m.id for m in registry.all_modules()}


class SalesSummaryQuery(BaseModel):
    """Re-validated body for read_sales_summary. No tenant field: scope is the header."""

    model_config = {"extra": "ignore"}
    limit: int = Field(default=10, ge=1, le=50)


class ModuleQuery(BaseModel):
    """Re-validated body for read_module. No tenant field: scope is the header."""

    model_config = {"extra": "ignore"}
    module: str | None = None


def _envelope(status_code: int, code: str, message: str) -> JSONResponse:
    """The named-error envelope every internal endpoint returns (genesis-build D)."""
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "error": {"code": code, "message": message}},
    )


def _pinned_tenant(request: Request) -> str:
    return request.headers.get(TENANT_HEADER, "").strip()


def _pinned_turn(request: Request) -> str:
    return request.headers.get(TURN_HEADER, "").strip() or None


def _guard(request: Request) -> "tuple[str | None, JSONResponse | None]":
    """Shared pre-flight for every internal op: internal-token present and a tenant
    pinned. Returns (phone, None) on success or (None, error_envelope) to return."""
    if not _has_internal_token(request):
        return None, _envelope(401, "unauthorized", "internal token required")
    phone = _pinned_tenant(request)
    if not phone:
        return None, _envelope(400, "tenant_unpinned", "no tenant pinned on the request")
    return phone, None


def _attention_item(item) -> dict:
    """Serialize one AttentionItem to a stable JSON shape. Severity goes out as both its
    int (sort key) and its name so the model never has to guess the ordinal."""
    return {
        "severity": int(item.severity),
        "severity_label": item.severity.name,
        "text": item.text,
        "action_label": item.action_label,
        "route": item.route,
        "module_id": item.module_id,
    }


@router.post("/internal/ops/read_stock")
def read_stock(request: Request):
    """Return current stock for the pinned tenant. Internal-token only.

    The body is ignored for scope: the tenant comes only from the pinned header,
    so a `phone` placed in the body by a confused or hostile caller changes
    nothing (D-037).
    """
    phone, err = _guard(request)
    if err:
        return err
    try:
        with tenant_scope(phone):
            rows = stock_service.get_current_stock(phone=phone, limit=500, offset=0)
        return JSONResponse(content={"ok": True, "stock": jsonable_encoder(rows)})
    except Exception:
        logger.exception("read_stock internal op failed for tenant %s", phone)
        return _envelope(500, "internal_error", "read_stock failed")


@router.post("/internal/ops/read_revenue")
def read_revenue(request: Request):
    """Return total revenue (ingresos) for the pinned tenant. Internal-token only."""
    phone, err = _guard(request)
    if err:
        return err
    try:
        with tenant_scope(phone):
            revenue = analytics_service.get_revenue(phone=phone)
        return JSONResponse(content={"ok": True, "revenue": jsonable_encoder(revenue)})
    except Exception:
        logger.exception("read_revenue internal op failed for tenant %s", phone)
        return _envelope(500, "internal_error", "read_revenue failed")


@router.post("/internal/ops/read_profit")
def read_profit(request: Request):
    """Return profit (ganancia) for the pinned tenant. Internal-token only."""
    phone, err = _guard(request)
    if err:
        return err
    try:
        with tenant_scope(phone):
            profit = analytics_service.get_profit(phone=phone)
        return JSONResponse(content={"ok": True, "profit": jsonable_encoder(profit)})
    except Exception:
        logger.exception("read_profit internal op failed for tenant %s", phone)
        return _envelope(500, "internal_error", "read_profit failed")


@router.post("/internal/ops/read_sales_summary")
def read_sales_summary(request: Request, payload: SalesSummaryQuery = Body(default=SalesSummaryQuery())):
    """Return a day-by-day paid-sales summary for the pinned tenant. Internal-token only.

    `limit` (1..50, default 10) is the only body field and is re-validated by Pydantic
    (AC4). The tenant is never a body field.
    """
    phone, err = _guard(request)
    if err:
        return err
    try:
        with tenant_scope(phone):
            rows = analytics_service.get_sales_summary(phone=phone, limit=payload.limit)
        return JSONResponse(content={"ok": True, "sales_summary": jsonable_encoder(rows)})
    except Exception:
        logger.exception("read_sales_summary internal op failed for tenant %s", phone)
        return _envelope(500, "internal_error", "read_sales_summary failed")


@router.post("/internal/ops/read_module")
def read_module(request: Request, payload: ModuleQuery = Body(default=ModuleQuery())):
    """Return one command-center module's headline + attention for the pinned tenant.

    `module` must be one of the eight registry ids (re-validated against MODULE_IDS,
    not trusted from the body); the provider's own `snapshot()` opens its own tenant
    scope, so this call does not double-scope.
    """
    phone, err = _guard(request)
    if err:
        return err
    module_id = (payload.module or "").strip()
    if module_id not in MODULE_IDS:
        return _envelope(400, "unknown_module", f"module must be one of {sorted(MODULE_IDS)}")
    try:
        module = next(m for m in registry.all_modules() if m.id == module_id)
        snap = module.snapshot(phone)  # provider self-scopes (protocol.py)
        return JSONResponse(content={
            "ok": True,
            "module": {
                "id": module_id,
                "label": module.label,
                "headline": jsonable_encoder(snap.headline),
                "attention": [_attention_item(i) for i in snap.attention],
            },
        })
    except Exception:
        logger.exception("read_module internal op failed for tenant %s module %s", phone, module_id)
        return _envelope(500, "internal_error", "read_module failed")


@router.post("/internal/ops/business_status")
def business_status(request: Request):
    """Return the ONE prioritized attention strip for the pinned tenant (AC6).

    This is `home_service.build_home(phone).attention` verbatim — the same list the
    command-center home renders, produced by `attention_service.aggregate()` plus
    `prioritize()`. It is not recomputed here and is not a second opinion: the chat and
    the dashboard answer "what needs attention" from one source. build_home fans the
    module snapshots out on its own pool and each provider self-scopes, so this call does
    not open a tenant scope of its own.
    """
    phone, err = _guard(request)
    if err:
        return err
    try:
        view = build_home(phone)
        return JSONResponse(content={
            "ok": True,
            "attention": [_attention_item(i) for i in view.attention],
        })
    except Exception:
        logger.exception("business_status internal op failed for tenant %s", phone)
        return _envelope(500, "internal_error", "business_status failed")


# ── Write-preview endpoints (spec 007 M3, D-038/D-040): stage, never commit ──────────
#
# Each preview re-validates inputs, resolves the product deterministically (never an
# arbitrary match), carries forward the salvaged write_agent guards (NULL-price block,
# ambiguity -> ask), and STAGES an op_token in the pending store with the exact db_args a
# later /chat/confirm will pass to the real operation. It returns a human preview; it
# commits nothing. The auto-vs-card verdict is NOT computed here — it is computed by the
# app (chat_service) against the operator's literal utterance this turn, so provenance can
# never be laundered through a model field or a tool result (D-041, D-042).


class SalePreview(BaseModel):
    model_config = {"extra": "ignore"}
    product: str | None = None
    quantity: int = Field(default=1, ge=1)
    unit_amount: float | None = None  # price per unit in currency units, as the operator said


class ExpensePreview(BaseModel):
    model_config = {"extra": "ignore"}
    amount: float | None = None
    description: str | None = None
    category: str | None = "GENERAL"


class StockPreview(BaseModel):
    model_config = {"extra": "ignore"}
    product: str | None = None
    quantity: int | None = None


def _money(cents) -> str:
    return f"${(cents or 0) / 100:,.0f}" if (cents or 0) % 100 == 0 else f"${(cents or 0) / 100:,.2f}"


@router.post("/internal/ops/preview/register_sale")
def preview_register_sale(request: Request, payload: SalePreview = Body(default=SalePreview())):
    phone, err = _guard(request)
    if err:
        return err
    try:
        with tenant_scope(phone):
            if not _rate_limit("register_sale"):
                return _rate_limited_envelope()
            res = ops_resolver.resolve_active_product(payload.product or "")
            if res.candidate_count == 0:
                return JSONResponse({"ok": True, "staged": False, "clarify": "no_product",
                                     "message": f"No encontré un producto que coincida con “{payload.product}”."})
            if res.candidate_count > 1:
                names = [c["name"] for c in res.candidates][:6]
                return JSONResponse({"ok": True, "staged": False, "clarify": "ambiguous_product",
                                     "candidates": names,
                                     "message": "Hay más de un producto que coincide: "
                                                + ", ".join(names) + ". ¿Cuál es?"})
            prod = res.product
            quantity = payload.quantity or 1
            if payload.unit_amount is not None:
                unit_price_cents = int(round(payload.unit_amount * 100))
            else:
                unit_price_cents = prod.get("unit_price_cents")
            # Salvaged NULL-price block (write_agent): never commit a sale with no price.
            if unit_price_cents is None:
                return JSONResponse({"ok": True, "staged": False, "clarify": "need_price",
                                     "message": f"¿A cuánto vendés {prod['name']}? No tengo un precio cargado."})
            line_total_cents = unit_price_cents * quantity
            # Load-bearing numerals that must trace to the utterance for an auto-post: the
            # unit price always, and the quantity when it is more than one.
            grounded = [unit_price_cents / 100.0]
            if quantity > 1:
                grounded.append(quantity)
            op_token = uuid.uuid4().hex
            args = {
                "operation_type": "REGISTER_SALE",
                "reversible": True,
                "product_name": prod["name"],
                "quantity": quantity,
                "unit_price_cents": unit_price_cents,
                "line_total_cents": line_total_cents,
                "grounded_amounts": grounded,
                "db_args": {
                    "status": "PAID",
                    "items": [{"product_id": prod["id"], "quantity": quantity,
                               "unit_price_cents": unit_price_cents}],
                },
            }
            pending_ops.stage(op_token=op_token, operation_type="REGISTER_SALE", args=args,
                              utterance=None, product_name=prod["name"], candidate_count=1,
                              turn_nonce=_pinned_turn(request))
        return JSONResponse({
            "ok": True, "staged": True, "op_token": op_token, "operation_type": "REGISTER_SALE",
            "reversible": True, "product_name": prod["name"],
            "summary": f"Venta: {quantity} × {prod['name']} a {_money(unit_price_cents)} = {_money(line_total_cents)}",
            "fields": {"producto": prod["name"], "cantidad": quantity,
                       "precio_unitario": _money(unit_price_cents), "total": _money(line_total_cents)},
        })
    except Exception:
        logger.exception("preview_register_sale failed for tenant %s", phone)
        return _envelope(500, "internal_error", "preview_register_sale failed")


@router.post("/internal/ops/preview/register_expense")
def preview_register_expense(request: Request, payload: ExpensePreview = Body(default=ExpensePreview())):
    phone, err = _guard(request)
    if err:
        return err
    if payload.amount is None or payload.amount <= 0:
        return JSONResponse({"ok": True, "staged": False, "clarify": "need_amount",
                             "message": "¿Cuánto fue el gasto?"})
    try:
        amount_cents = int(round(payload.amount * 100))
        description = (payload.description or "Gasto").strip()
        category = (payload.category or "GENERAL").strip() or "GENERAL"
        op_token = uuid.uuid4().hex
        args = {
            "operation_type": "REGISTER_EXPENSE",
            "reversible": True,
            "product_name": None,
            "amount_cents": amount_cents,
            "description": description,
            "category": category,
            "grounded_amounts": [payload.amount],
            "db_args": {"amount_cents": amount_cents, "description": description, "category": category},
        }
        with tenant_scope(phone):
            if not _rate_limit("register_expense"):
                return _rate_limited_envelope()
            pending_ops.stage(op_token=op_token, operation_type="REGISTER_EXPENSE", args=args,
                              utterance=None, product_name=None, candidate_count=1,
                              turn_nonce=_pinned_turn(request))
        return JSONResponse({
            "ok": True, "staged": True, "op_token": op_token, "operation_type": "REGISTER_EXPENSE",
            "reversible": True, "product_name": None,
            "summary": f"Gasto: {_money(amount_cents)} ({description})",
            "fields": {"monto": _money(amount_cents), "descripcion": description, "categoria": category},
        })
    except Exception:
        logger.exception("preview_register_expense failed for tenant %s", phone)
        return _envelope(500, "internal_error", "preview_register_expense failed")


@router.post("/internal/ops/preview/add_stock")
def preview_add_stock(request: Request, payload: StockPreview = Body(default=StockPreview())):
    phone, err = _guard(request)
    if err:
        return err
    if not payload.quantity or payload.quantity <= 0:
        return JSONResponse({"ok": True, "staged": False, "clarify": "need_quantity",
                             "message": "¿Cuántas unidades agrego?"})
    try:
        with tenant_scope(phone):
            if not _rate_limit("add_stock"):
                return _rate_limited_envelope()
            res = ops_resolver.resolve_active_product(payload.product or "")
            if res.candidate_count == 0:
                return JSONResponse({"ok": True, "staged": False, "clarify": "no_product",
                                     "message": f"No encontré un producto que coincida con “{payload.product}”."})
            if res.candidate_count > 1:
                names = [c["name"] for c in res.candidates][:6]
                return JSONResponse({"ok": True, "staged": False, "clarify": "ambiguous_product",
                                     "candidates": names,
                                     "message": "Hay más de un producto que coincide: "
                                                + ", ".join(names) + ". ¿Cuál es?"})
            prod = res.product
            quantity = payload.quantity
            op_token = uuid.uuid4().hex
            args = {
                "operation_type": "ADD_STOCK",
                "reversible": True,
                "product_name": prod["name"],
                "quantity": quantity,
                "grounded_amounts": [quantity],
                "db_args": {"product_id": prod["id"], "quantity": quantity,
                            "reason": "Alta de stock por chat"},
            }
            pending_ops.stage(op_token=op_token, operation_type="ADD_STOCK", args=args,
                              utterance=None, product_name=prod["name"], candidate_count=1,
                              turn_nonce=_pinned_turn(request))
        return JSONResponse({
            "ok": True, "staged": True, "op_token": op_token, "operation_type": "ADD_STOCK",
            "reversible": True, "product_name": prod["name"],
            "summary": f"Agregar stock: {quantity} u de {prod['name']}",
            "fields": {"producto": prod["name"], "cantidad": quantity},
        })
    except Exception:
        logger.exception("preview_add_stock failed for tenant %s", phone)
        return _envelope(500, "internal_error", "preview_add_stock failed")


# ── M4 confirm-only previews (D-044): irreversible / bulk / destructive — never auto ──
#
# These stage like the reversible set but with irreversible=True (or simply outside the
# reversible set), so the server verdict is always auto:false and the owner clicks a card
# that shows the exact target and an irreversibility flag (AC11). A batch confirms ONCE for
# the whole set, itemized. Every call is rate-limited and audited (AC12), tighter on the
# destructive cancel/deactivate ops.


class PricePreview(BaseModel):
    model_config = {"extra": "ignore"}
    product: str | None = None
    new_amount: float | None = None


class ProductPreview(BaseModel):
    model_config = {"extra": "ignore"}
    name: str | None = None
    price_amount: float | None = None
    cost_amount: float = 0.0


class BatchItem(BaseModel):
    model_config = {"extra": "ignore"}
    name: str
    price_amount: float | None = None
    cost_amount: float = 0.0


class BatchPreview(BaseModel):
    model_config = {"extra": "ignore"}
    products: list[BatchItem] = Field(default_factory=list)


class DeactivatePreview(BaseModel):
    model_config = {"extra": "ignore"}
    product: str | None = None


def _rate_limit(op_name: str) -> bool:
    """Call INSIDE an open tenant_scope: enforce the per-tenant cap and audit the call."""
    ok = ops_guard.within_caps(op_name)
    ops_guard.audit(op_name, caller="gateway", outcome="ok" if ok else "rate_limited")
    return ok


def _rate_limited_envelope() -> JSONResponse:
    return _envelope(429, "rate_limited", "demasiadas operaciones seguidas, probá en un momento")


def _sku_ph() -> str:
    import database_config
    return "%s" if getattr(database_config, "USE_POSTGRES", False) else "?"


def _gen_sku(name: str, seen: set | None = None) -> str:
    """A simple, unique SKU from a product name (salvaged intent of write_agent's SKU gen):
    an uppercased slug prefix plus a numeric suffix until unique in the tenant catalog AND
    not already allocated earlier in the same batch (``seen`` — two same-named items in one
    register_products_batch must not resolve to the same SKU, council L7)."""
    import re as _re
    slug = _re.sub(r"[^A-Za-z0-9]+", "-", (name or "PROD").strip()).strip("-").upper()[:16] or "PROD"
    q = f"SELECT 1 FROM products WHERE sku = {_sku_ph()}"
    candidate = slug
    n = 2
    while (seen is not None and candidate in seen) or fetch_one(q, (candidate,)):
        candidate = f"{slug}-{n}"
        n += 1
    if seen is not None:
        seen.add(candidate)
    return candidate


@router.post("/internal/ops/preview/update_product_price")
def preview_update_product_price(request: Request, payload: PricePreview = Body(default=PricePreview())):
    phone, err = _guard(request)
    if err:
        return err
    if payload.new_amount is None or payload.new_amount < 0:
        return JSONResponse({"ok": True, "staged": False, "clarify": "need_amount",
                             "message": "¿A qué precio lo dejo?"})
    try:
        with tenant_scope(phone):
            if not _rate_limit("update_product_price"):
                return _rate_limited_envelope()
            res = ops_resolver.resolve_active_product(payload.product or "")
            if res.candidate_count == 0:
                return JSONResponse({"ok": True, "staged": False, "clarify": "no_product",
                                     "message": f"No encontré “{payload.product}”."})
            if res.candidate_count > 1:
                names = [c["name"] for c in res.candidates][:6]
                return JSONResponse({"ok": True, "staged": False, "clarify": "ambiguous_product",
                                     "candidates": names, "message": "¿Cuál? " + ", ".join(names)})
            prod = res.product
            new_cents = int(round(payload.new_amount * 100))
            op_token = uuid.uuid4().hex
            args = {
                "operation_type": "UPDATE_PRODUCT_PRICE", "reversible": False, "irreversible": True,
                "product_name": prod["name"], "unit_price_cents": new_cents,
                "summary": f"Cambiar precio de {prod['name']}: {_money(prod.get('unit_price_cents'))} → {_money(new_cents)}",
                "fields": {"producto": prod["name"], "precio anterior": _money(prod.get("unit_price_cents")),
                           "precio nuevo": _money(new_cents)},
                "db_args": {"product_id": prod["id"], "unit_price_cents": new_cents},
            }
            pending_ops.stage(op_token=op_token, operation_type="UPDATE_PRODUCT_PRICE", args=args,
                              utterance=None, product_name=prod["name"], candidate_count=1, turn_nonce=_pinned_turn(request))
        return JSONResponse({"ok": True, "staged": True, "op_token": op_token,
                             "operation_type": "UPDATE_PRODUCT_PRICE", "reversible": False,
                             "irreversible": True, "product_name": prod["name"],
                             "summary": args["summary"], "fields": args["fields"]})
    except Exception:
        logger.exception("preview_update_product_price failed for tenant %s", phone)
        return _envelope(500, "internal_error", "preview_update_product_price failed")


@router.post("/internal/ops/preview/register_product")
def preview_register_product(request: Request, payload: ProductPreview = Body(default=ProductPreview())):
    phone, err = _guard(request)
    if err:
        return err
    if not payload.name or payload.price_amount is None or payload.price_amount < 0:
        return JSONResponse({"ok": True, "staged": False, "clarify": "need_fields",
                             "message": "Para crear un producto necesito el nombre y el precio."})
    try:
        with tenant_scope(phone):
            if not _rate_limit("register_product"):
                return _rate_limited_envelope()
            name = payload.name.strip()
            price_cents = int(round(payload.price_amount * 100))
            cost_cents = int(round((payload.cost_amount or 0) * 100))
            sku = _gen_sku(name)
            op_token = uuid.uuid4().hex
            args = {
                "operation_type": "REGISTER_PRODUCT", "reversible": False, "irreversible": True,
                "product_name": name,
                "summary": f"Crear producto: {name} a {_money(price_cents)} (SKU {sku})",
                "fields": {"nombre": name, "precio": _money(price_cents), "SKU": sku},
                "db_args": {"sku": sku, "name": name, "unit_price_cents": price_cents,
                            "unit_cost_cents": cost_cents},
            }
            pending_ops.stage(op_token=op_token, operation_type="REGISTER_PRODUCT", args=args,
                              utterance=None, product_name=name, candidate_count=1, turn_nonce=_pinned_turn(request))
        return JSONResponse({"ok": True, "staged": True, "op_token": op_token,
                             "operation_type": "REGISTER_PRODUCT", "reversible": False,
                             "irreversible": True, "product_name": name,
                             "summary": args["summary"], "fields": args["fields"]})
    except Exception:
        logger.exception("preview_register_product failed for tenant %s", phone)
        return _envelope(500, "internal_error", "preview_register_product failed")


@router.post("/internal/ops/preview/register_products_batch")
def preview_register_products_batch(request: Request, payload: BatchPreview = Body(default=BatchPreview())):
    phone, err = _guard(request)
    if err:
        return err
    items = [p for p in (payload.products or []) if p.name and p.price_amount is not None]
    if not items:
        return JSONResponse({"ok": True, "staged": False, "clarify": "need_fields",
                             "message": "Decime los productos con su nombre y precio."})
    try:
        with tenant_scope(phone):
            if not _rate_limit("register_products_batch"):
                return _rate_limited_envelope()
            products = []
            fields = {}
            seen_skus: set = set()
            for p in items:
                price_cents = int(round(p.price_amount * 100))
                sku = _gen_sku(p.name.strip(), seen_skus)
                products.append({"sku": sku, "name": p.name.strip(), "unit_price_cents": price_cents,
                                 "unit_cost_cents": int(round((p.cost_amount or 0) * 100))})
                fields[p.name.strip()] = _money(price_cents)
            op_token = uuid.uuid4().hex
            args = {
                "operation_type": "REGISTER_PRODUCTS_BATCH", "reversible": False, "irreversible": True,
                "product_name": None,
                "summary": f"Crear {len(products)} productos de una vez",
                "fields": fields,
                "db_args": {"products": products},
            }
            pending_ops.stage(op_token=op_token, operation_type="REGISTER_PRODUCTS_BATCH", args=args,
                              utterance=None, product_name=None, candidate_count=1, turn_nonce=_pinned_turn(request))
        return JSONResponse({"ok": True, "staged": True, "op_token": op_token,
                             "operation_type": "REGISTER_PRODUCTS_BATCH", "reversible": False,
                             "irreversible": True, "summary": args["summary"], "fields": fields,
                             "count": len(products)})
    except Exception:
        logger.exception("preview_register_products_batch failed for tenant %s", phone)
        return _envelope(500, "internal_error", "preview_register_products_batch failed")


@router.post("/internal/ops/preview/deactivate_product")
def preview_deactivate_product(request: Request, payload: DeactivatePreview = Body(default=DeactivatePreview())):
    phone, err = _guard(request)
    if err:
        return err
    try:
        with tenant_scope(phone):
            if not _rate_limit("deactivate_product"):
                return _rate_limited_envelope()
            res = ops_resolver.resolve_active_product(payload.product or "")
            if res.candidate_count == 0:
                return JSONResponse({"ok": True, "staged": False, "clarify": "no_product",
                                     "message": f"No encontré “{payload.product}”."})
            if res.candidate_count > 1:
                names = [c["name"] for c in res.candidates][:6]
                return JSONResponse({"ok": True, "staged": False, "clarify": "ambiguous_product",
                                     "candidates": names, "message": "¿Cuál? " + ", ".join(names)})
            prod = res.product
            op_token = uuid.uuid4().hex
            args = {
                "operation_type": "DEACTIVATE_PRODUCT", "reversible": False, "irreversible": True,
                "product_name": prod["name"],
                "summary": f"Desactivar producto: {prod['name']} (SKU {prod.get('sku')})",
                "fields": {"producto": prod["name"], "SKU": prod.get("sku")},
                "db_args": {"product_id": prod["id"]},
            }
            pending_ops.stage(op_token=op_token, operation_type="DEACTIVATE_PRODUCT", args=args,
                              utterance=None, product_name=prod["name"], candidate_count=1, turn_nonce=_pinned_turn(request))
        return JSONResponse({"ok": True, "staged": True, "op_token": op_token,
                             "operation_type": "DEACTIVATE_PRODUCT", "reversible": False,
                             "irreversible": True, "product_name": prod["name"],
                             "summary": args["summary"], "fields": args["fields"]})
    except Exception:
        logger.exception("preview_deactivate_product failed for tenant %s", phone)
        return _envelope(500, "internal_error", "preview_deactivate_product failed")


@router.post("/internal/ops/preview/cancel_last_operation")
def preview_cancel_last_operation(request: Request):
    phone, err = _guard(request)
    if err:
        return err
    try:
        with tenant_scope(phone):
            if not _rate_limit("cancel_last_operation"):
                return _rate_limited_envelope()
            last = get_last_operation()
            if not last:
                return JSONResponse({"ok": True, "staged": False, "clarify": "nothing_to_cancel",
                                     "message": "No veo una operación reciente para cancelar."})
            kind = last["type"]
            data = last["data"]
            if kind == "SALE":
                target = f"venta #{data.get('sale_number', data.get('id'))} por {_money(data.get('total_amount_cents'))}"
                db_args = {"kind": "SALE", "sale_id": data["id"]}
            elif kind == "EXPENSE":
                target = f"gasto: {data.get('description')} por {_money(data.get('amount_cents'))}"
                db_args = {"kind": "EXPENSE", "expense_id": data["id"]}
            else:  # STOCK
                target = f"+{data.get('quantity')} u de {data.get('product_name')}"
                db_args = {"kind": "STOCK", "movement_id": data["id"]}
            op_token = uuid.uuid4().hex
            args = {
                "operation_type": "CANCEL_LAST_OPERATION", "reversible": False, "irreversible": False,
                "product_name": None,
                "summary": f"Cancelar la última operación: {target}",
                "fields": {"operación": target},
                "db_args": db_args,
            }
            pending_ops.stage(op_token=op_token, operation_type="CANCEL_LAST_OPERATION", args=args,
                              utterance=None, product_name=None, candidate_count=1, turn_nonce=_pinned_turn(request))
        return JSONResponse({"ok": True, "staged": True, "op_token": op_token,
                             "operation_type": "CANCEL_LAST_OPERATION", "reversible": False,
                             "irreversible": False, "summary": args["summary"], "fields": args["fields"]})
    except Exception:
        logger.exception("preview_cancel_last_operation failed for tenant %s", phone)
        return _envelope(500, "internal_error", "preview_cancel_last_operation failed")
