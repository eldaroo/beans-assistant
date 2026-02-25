"""Chat Simulation API Endpoint."""

import logging
from pathlib import Path
import sys

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.services.chat_service import ChatService

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    """Chat message input."""

    phone: str
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "phone": "+5491112345678",
                "message": "cuántos productos tengo?",
            }
        }


class ChatResponse(BaseModel):
    """Chat response output."""

    phone: str
    user_message: str
    bot_response: str
    metadata: dict = Field(default_factory=dict)


@router.post("/chat/simulate", response_model=ChatResponse)
async def simulate_chat(chat: ChatMessage):
    """Simulate one chat message and return bot response."""
    try:
        bot_response, metadata = ChatService.simulate_chat(phone=chat.phone, message=chat.message)
        return ChatResponse(
            phone=chat.phone,
            user_message=chat.message,
            bot_response=bot_response,
            metadata=metadata,
        )
    except Exception:
        logger.exception("Error processing simulate_chat")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing message",
        )


@router.post("/chat/simulate/batch", response_model=list[ChatResponse])
async def simulate_chat_batch(messages: list[ChatMessage]):
    """Simulate multiple chat messages in sequence."""
    responses = []
    for chat in messages:
        try:
            responses.append(await simulate_chat(chat))
        except HTTPException as exc:
            responses.append(
                ChatResponse(
                    phone=chat.phone,
                    user_message=chat.message,
                    bot_response=f"Error: {exc.detail}",
                    metadata={"error": True},
                )
            )
        except Exception:
            logger.exception("Unexpected error processing batch chat item")
            responses.append(
                ChatResponse(
                    phone=chat.phone,
                    user_message=chat.message,
                    bot_response="Error: Error processing message",
                    metadata={"error": True},
                )
            )

    return responses
