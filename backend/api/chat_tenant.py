"""Chat API Endpoint for Tenant-Specific Conversations."""

import logging
from pathlib import Path
import sys

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

import database_config
from backend import cache
from backend.auth.dependencies import require_tenant_match, require_tenant_session
from backend.repositories import pending_ops_repository as pending_ops
from backend.services import ops_guard
from backend.services.chat_service import ChatService, ChatTenantNotFoundError
from database_config import fetch_one, tenant_context
from tenant_manager import TenantManager

router = APIRouter()
logger = logging.getLogger(__name__)


class TenantChatMessage(BaseModel):
    """Chat message input for tenant-specific chat."""

    message: str
    sender_name: str | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "message": "cuántos productos tengo?",
            }
        }


class TenantChatResponse(BaseModel):
    """Chat response output."""

    response: str
    metadata: dict = Field(default_factory=dict)


@router.post("/{phone}/chat", response_model=TenantChatResponse)
def chat_with_tenant(phone: str, chat: TenantChatMessage):
    """Chat with the AI agent in the context of a specific tenant database.

    Sync (not async) on purpose: the agent path makes a BLOCKING call to the gateway, and the
    gateway calls BACK into this app's /internal/ops/* for its tools. An async handler would block
    the event loop for the whole agent turn and deadlock that nested call; a sync handler runs in
    FastAPI's threadpool, so the loop stays free to serve the tool callback concurrently.
    """
    logger.info(f"chat_with_tenant endpoint: phone={phone}, message={chat.message[:50]}...")
    try:
        logger.info(f"chat_with_tenant endpoint: calling ChatService.chat_with_tenant")
        envelope = ChatService.chat_with_tenant(
            phone=phone,
            message=chat.message,
            sender_name=chat.sender_name,
        )
        response = envelope["response"]
        metadata = envelope.get("metadata") or {}
        logger.info(f"chat_with_tenant endpoint: got response={response[:50]}...")
        return TenantChatResponse(response=response, metadata=metadata)
    except ChatTenantNotFoundError as exc:
        logger.warning(f"chat_with_tenant endpoint: tenant not found - {exc}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except HTTPException:
        logger.warning(f"chat_with_tenant endpoint: HTTPException raised")
        raise
    except Exception as e:
        logger.exception(f"chat_with_tenant endpoint: ERROR - {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing message",
        )


class ThreadTurn(BaseModel):
    """One prior conversation turn for rehydration (spec 006 T-009)."""

    role: str
    content: str


class TenantChatThread(BaseModel):
    """The server-side conversation thread for a tenant, for rehydration.

    The chat widget reads this when its own sessionStorage copy is empty, so a
    returning owner sees the conversation that was already established
    server-side rather than a blank Timonel (AC4).
    """

    thread: list[ThreadTurn] = Field(default_factory=list)


@router.get("/{phone}/chat/thread", response_model=TenantChatThread)
async def chat_thread(phone: str, _user: dict = Depends(require_tenant_match)):
    """Return the server-side conversation thread for a tenant (spec 006 T-009).

    Owner-gated by the same ``require_tenant_match`` dependency the home uses:
    this endpoint returns conversation CONTENT, so an owner may read only her
    own thread (admin and internal-token callers bypass as elsewhere). The
    widget calls it from an already owner-gated page, so the session cookie is
    present and the check is transparent to the real caller.

    Source of truth is the same in-process conversation memory the dispatcher
    keeps (spec 001). It is read-only and lean (role + text per turn); empty and
    stale threads come back as an empty list. Never raises for an unknown or
    quiet tenant — a blank thread is a valid answer, and the widget then falls
    back to the proactive greeting.
    """
    turns = ChatService.get_history(phone)
    return TenantChatThread(thread=[ThreadTurn(role=t["role"], content=t["content"]) for t in turns])


class TenantGreeting(BaseModel):
    """Proactive greeting payload returned to the chat widget on first open.

    `kind` lets the frontend pick a copy variant if we add more cases later
    (low_stock, etc). For now the only kind that returns a non-null
    `greeting` is `empty_catalog`.
    """

    greeting: str | None
    kind: str | None = None


_EMPTY_CATALOG_GREETING = (
    "Veo que estas arrancando con el catalogo vacio. "
    "Querés que carguemos los primeros productos juntos? "
    "Decime que vendes y los agrego."
)


@router.get("/{phone}/chat/greeting", response_model=TenantGreeting)
async def chat_greeting(phone: str):
    """Return a proactive opening message based on tenant catalog state.

    Called by the chat widget once when it opens, gated by a localStorage
    flag on the frontend so we don't re-greet on every page load. When the
    tenant has at least one active product, returns `greeting: null` and
    the widget renders nothing extra. When the tenant has zero active
    products, returns the empty-catalog greeting so the user gets a
    proactive nudge instead of staring at an empty input box.
    """
    tenant_manager = TenantManager()
    normalized_phone = tenant_manager.normalize_phone_number(phone)
    resolved_phone = tenant_manager.resolve_tenant_phone(normalized_phone)
    if not resolved_phone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {normalized_phone} not found",
        )

    with tenant_context(resolved_phone):
        # EXISTS is cheaper than COUNT and stops at the first row;
        # idx_products_is_active backs the predicate.
        row = fetch_one(
            "SELECT EXISTS(SELECT 1 FROM products WHERE is_active = TRUE) AS has_products"
        )
    has_products = bool(row and row.get("has_products"))

    if has_products:
        return TenantGreeting(greeting=None)
    return TenantGreeting(greeting=_EMPTY_CATALOG_GREETING, kind="empty_catalog")


# ── Two-phase write commit + Undo (spec 007 M3, D-040/D-043) ─────────────────────────
#
# /chat/confirm is the single write-commit capability and the model has no tool that
# reaches it; /chat/undo is the pre-authorized system path the Undo toast fires. BOTH are
# gated by require_tenant_session (session cookie only, never the internal token), so only
# the owner's own browser can commit or undo — whether the confirm click is manual or
# client-auto-submitted for a reversible, grounded write. Sync handlers (threadpool), like
# the chat route.


class ConfirmBody(BaseModel):
    op_token: str


def _money(cents) -> str:
    return f"${(cents or 0) / 100:,.0f}" if (cents or 0) % 100 == 0 else f"${(cents or 0) / 100:,.2f}"


def _resolve(phone: str) -> str:
    tm = TenantManager()
    resolved = tm.resolve_tenant_phone(tm.normalize_phone_number(phone))
    if not resolved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant {phone} not found")
    return resolved


# The reversible set (clean one-tap Undo). Everything else commits confirm-only and shows
# no Undo toast — the operator confirmed it deliberately and it has no clean inverse (D-044).
_REVERSIBLE_OPS = {"REGISTER_SALE", "REGISTER_EXPENSE", "ADD_STOCK"}


def _commit_op(op_type: str, db_args: dict):
    """Dispatch the staged op to its real operation (the single commit point). Raises
    ValueError on a guard rejection (caught by the route for a pessimistic non-post)."""
    if op_type == "REGISTER_SALE":
        return database_config.register_sale(db_args)
    if op_type == "REGISTER_EXPENSE":
        return database_config.register_expense(db_args)
    if op_type == "ADD_STOCK":
        return database_config.add_stock(db_args)
    if op_type == "UPDATE_PRODUCT_PRICE":
        return database_config.update_product_price(db_args["product_id"], db_args["unit_price_cents"])
    if op_type == "REGISTER_PRODUCT":
        return database_config.register_product(db_args)
    if op_type == "REGISTER_PRODUCT_WITH_STOCK":
        return database_config.register_product_with_stock(db_args)
    if op_type == "REGISTER_PRODUCTS_BATCH":
        return database_config.register_products_batch(db_args["products"])
    if op_type == "DEACTIVATE_PRODUCT":
        return database_config.deactivate_product(db_args["product_id"])
    if op_type == "CANCEL_SALE":
        return database_config.cancel_sale(db_args["sale_id"])
    if op_type == "CANCEL_EXPENSE":
        return database_config.cancel_expense(db_args["expense_id"])
    if op_type == "CANCEL_STOCK":
        return database_config.cancel_stock_movement(db_args["movement_id"])
    if op_type == "CANCEL_LAST_OPERATION":
        kind = db_args.get("kind")
        if kind == "SALE":
            return database_config.cancel_sale(db_args["sale_id"])
        if kind == "EXPENSE":
            return database_config.cancel_expense(db_args["expense_id"])
        if kind == "STOCK":
            return database_config.cancel_stock_movement(db_args["movement_id"])
        raise ValueError("No hay una operación reciente para cancelar.")
    return None  # unknown / non-committable


def _receipt(op: dict, result: dict) -> dict:
    """Build the committed-receipt viewmodel from the commit result + staged args.

    Names the target, the amount, and the resulting per-book balance from the commit
    response (AC10). For a reversible op it carries the undo handle + Undo-toast label
    (AC17); for a confirm-only op it carries no undo handle (no Undo toast)."""
    args = op.get("args") or {}
    op_type = op["operation_type"]
    name = args.get("product_name")
    result = result or {}
    amount_label, balance_label, undo_handle = "", "", {}
    if op_type == "REGISTER_SALE":
        amount = _money(args.get("line_total_cents"))
        text = f"Anotado: venta de {name} por {amount}."
        amount_label = f"−{amount}"
        balance_label = f"Ventas: ${result.get('revenue_usd', 0):,.0f}"
        undo_handle = {"sale_id": result.get("sale_id")}
    elif op_type == "REGISTER_EXPENSE":
        amount = _money(args.get("amount_cents"))
        text = f"Anotado: gasto de {amount} ({args.get('description')})."
        amount_label = f"−{amount}"
        balance_label = f"Ganancia: ${result.get('profit_usd', 0):,.0f}"
        undo_handle = {"expense_id": result.get("expense_id")}
    elif op_type == "ADD_STOCK":
        qty = args.get("quantity")
        text = f"Anotado: +{qty} u de {name}."
        amount_label = f"+{qty} u"
        balance_label = f"Stock: {result.get('current_stock')} u"
        undo_handle = {"movement_id": result.get("movement_id")}
    elif op_type == "UPDATE_PRODUCT_PRICE":
        text = f"Precio actualizado: {name} a {_money(args.get('unit_price_cents'))}."
    elif op_type in ("REGISTER_PRODUCT", "REGISTER_PRODUCT_WITH_STOCK"):
        text = f"Producto creado: {name}."
    elif op_type == "REGISTER_PRODUCTS_BATCH":
        rows = result.get("result") if isinstance(result, dict) else result
        rows = rows if isinstance(rows, list) else []
        created = sum(1 for r in rows if isinstance(r, dict) and r.get("status") == "created")
        text = f"Catálogo: {created} producto(s) creado(s)."
    elif op_type == "DEACTIVATE_PRODUCT":
        text = f"Producto desactivado: {name}."
    elif op_type in ("CANCEL_SALE", "CANCEL_EXPENSE", "CANCEL_STOCK", "CANCEL_LAST_OPERATION"):
        text = "Operación cancelada."
    else:
        text = "Anotado."
    return {
        "text": text,
        "title": text,
        "amount_label": amount_label,
        "balance_label": balance_label,
        "undo_handle": undo_handle,
    }


@router.post("/{phone}/chat/confirm")
def chat_confirm(phone: str, body: ConfirmBody, request: Request):
    """Commit a staged write exactly once (the single non-model write capability).

    Idempotent: a second confirm of the same op_token returns the same committed receipt
    and does not write twice. Pessimistic (AC16): if the operation rejects at commit time
    (e.g. register_sale's stock-availability guard), nothing is marked committed, no
    receipt is returned, and the reply names why it could not post.
    """
    require_tenant_session(request, phone)
    resolved = _resolve(phone)
    with tenant_context(resolved):
        op = pending_ops.get(body.op_token)
        if not op:
            return {"ok": False, "committed": False,
                    "error": {"code": "unknown_op", "message": "No encuentro esa operación."}}
        if op["status"] == "CANCELLED":
            return {"ok": True, "committed": False, "cancelled": True,
                    "message": "Esa operación ya fue deshecha."}
        op_type = op["operation_type"]
        reversible = op_type in _REVERSIBLE_OPS
        if op["status"] == "COMMITTED":
            # Idempotent double-submit: return the stored receipt, commit nothing new.
            result = op.get("commit_result") or {}
            return {"ok": True, "committed": True, "idempotent": True,
                    "op_token": body.op_token, "operation_type": op_type, "reversible": reversible,
                    "receipt": _receipt(op, result)}

        # Claim the op atomically BEFORE the side effect (council B1/H2). Only the single
        # winner of PENDING->COMMITTING runs the real write, so two concurrent/retried confirms
        # of one op_token can never both post. A loser re-reads: the winner will have committed.
        if not pending_ops.claim(body.op_token):
            op2 = pending_ops.get(body.op_token)
            if op2 and op2["status"] == "COMMITTED":
                return {"ok": True, "committed": True, "idempotent": True, "op_token": body.op_token,
                        "operation_type": op_type, "reversible": reversible,
                        "receipt": _receipt(op2, op2.get("commit_result") or {})}
            if op2 and op2["status"] == "CANCELLED":
                return {"ok": True, "committed": False, "cancelled": True,
                        "message": "Esa operación ya fue deshecha."}
            return {"ok": True, "committed": False, "op_token": body.op_token,
                    "message": "Esa operación se está procesando."}

        db_args = (op.get("args") or {}).get("db_args") or {}
        try:
            result = _commit_op(op_type, db_args)
            if result is None:
                pending_ops.unclaim(body.op_token)
                return {"ok": False, "committed": False,
                        "error": {"code": "not_committable",
                                  "message": f"La operación {op_type} no se confirma por este camino."}}
        except ValueError as exc:
            # Pessimistic post (AC16): the guard rejected (e.g. not enough stock). Release the
            # claim back to PENDING (a retry can work later), render no receipt, say why.
            logger.info("chat_confirm: op %s rejected at commit: %s", body.op_token, exc)
            pending_ops.unclaim(body.op_token)
            ops_guard.audit(op_type, args={"op_token": body.op_token}, caller="owner",
                            op_token=body.op_token, outcome="rejected")
            return {"ok": True, "committed": False, "op_token": body.op_token,
                    "message": str(exc)}
        except Exception:
            logger.exception("chat_confirm: commit failed for op %s", body.op_token)
            pending_ops.unclaim(body.op_token)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="No se pudo confirmar la operación")

        pending_ops.mark_committed(body.op_token, result if isinstance(result, dict) else {"result": result})
        ops_guard.audit(op_type, args={"op_token": body.op_token}, caller="owner",
                        op_token=body.op_token, outcome="committed")
        try:
            cache.invalidate_all(resolved)
        except Exception:
            logger.exception("chat_confirm: cache invalidation failed (non-fatal)")
        return {"ok": True, "committed": True, "op_token": body.op_token,
                "operation_type": op_type, "reversible": reversible, "receipt": _receipt(op, result)}


@router.post("/{phone}/chat/undo")
def chat_undo(phone: str, body: ConfirmBody, request: Request):
    """Reverse a committed reversible write via the append-inverse compensator (AC15).

    This is the pre-authorized SYSTEM path the Undo toast fires — NOT an operator CANCEL
    (which is itself confirm-only in M4). It claims the op atomically (COMMITTED->CANCELLING)
    so a double Undo tap compensates AT MOST ONCE even though cancel_stock_movement is not
    itself idempotent (council H4); the compensator runs only for the single winner, then the
    op finalizes to CANCELLED (or reverts to COMMITTED if the compensator failed, so Undo can
    be retried).
    """
    require_tenant_session(request, phone)
    resolved = _resolve(phone)
    with tenant_context(resolved):
        op = pending_ops.get(body.op_token)
        if not op:
            return {"ok": False, "undone": False,
                    "error": {"code": "unknown_op", "message": "No encuentro esa operación."}}
        if op["status"] in ("CANCELLED", "CANCELLING"):
            return {"ok": True, "undone": True, "already": True, "message": "Ya estaba deshecho."}
        if op["status"] != "COMMITTED":
            return {"ok": False, "undone": False,
                    "error": {"code": "not_committed", "message": "Esa operación no está confirmada."}}

        op_type = op["operation_type"]
        if op_type not in ("REGISTER_SALE", "REGISTER_EXPENSE", "ADD_STOCK"):
            return {"ok": False, "undone": False,
                    "error": {"code": "not_reversible", "message": "Esa operación no se puede deshacer así."}}

        # Atomic claim: only the winner of COMMITTED->CANCELLING compensates (H4).
        if not pending_ops.claim_cancel(body.op_token):
            return {"ok": True, "undone": True, "already": True, "message": "Ya estaba deshecho."}

        result = op.get("commit_result") or {}
        try:
            if op_type == "REGISTER_SALE":
                out = database_config.cancel_sale(result.get("sale_id"))
            elif op_type == "REGISTER_EXPENSE":
                out = database_config.cancel_expense(result.get("expense_id"))
            else:  # ADD_STOCK
                out = database_config.cancel_stock_movement(result.get("movement_id"))
        except Exception:
            logger.exception("chat_undo: compensator failed for op %s", body.op_token)
            pending_ops.revert_cancel(body.op_token)  # allow a retry; nothing was double-restored
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="No se pudo deshacer la operación")

        pending_ops.finalize_cancelled(body.op_token)
        ops_guard.audit("undo:" + op_type, args={"op_token": body.op_token}, caller="owner",
                        op_token=body.op_token, outcome="undone")
        try:
            cache.invalidate_all(resolved)
        except Exception:
            logger.exception("chat_undo: cache invalidation failed (non-fatal)")
        return {"ok": True, "undone": True, "op_token": body.op_token, "result": out}
