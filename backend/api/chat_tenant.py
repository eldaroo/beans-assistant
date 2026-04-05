"""Chat API Endpoint for Tenant-Specific Conversations."""

import logging
from pathlib import Path
import sys

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.services.chat_service import ChatService, ChatTenantNotFoundError

router = APIRouter()
logger = logging.getLogger(__name__)


class TenantChatMessage(BaseModel):
    """Chat message input for tenant-specific chat."""

    message: str

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
        response, metadata = ChatService.chat_with_tenant(phone=phone, message=chat.message)
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
