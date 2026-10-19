"""Chat API Endpoint for Tenant-Specific Conversations."""

import logging
from pathlib import Path
import sys

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.auth.dependencies import require_tenant_match
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
async def chat_with_tenant(phone: str, chat: TenantChatMessage):
    """Chat with the AI agent in the context of a specific tenant database."""
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
