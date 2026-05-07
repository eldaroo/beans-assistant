"""Chat API Endpoint for Tenant-Specific Conversations."""

import logging
from pathlib import Path
import sys

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

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
        response, metadata = ChatService.chat_with_tenant(
            phone=phone,
            message=chat.message,
            sender_name=chat.sender_name,
        )
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
