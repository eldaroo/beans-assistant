"""WhatsApp onboarding API endpoint."""

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.services.onboarding_service import OnboardingService

router = APIRouter()
logger = logging.getLogger(__name__)
onboarding_service = OnboardingService()


class OnboardingMessage(BaseModel):
    """Incoming onboarding message."""

    message: str
    sender_name: str | None = None


class OnboardingResponse(BaseModel):
    """Outgoing onboarding response."""

    response: str
    metadata: dict = Field(default_factory=dict)


@router.post("/{phone}", response_model=OnboardingResponse)
async def handle_onboarding(phone: str, payload: OnboardingMessage):
    """Handle a single onboarding turn for a phone number."""
    try:
        result = onboarding_service.handle_message(
            phone=phone,
            message=payload.message,
            sender_name=payload.sender_name,
        )
        return OnboardingResponse(**result)
    except Exception:
        logger.exception("Failed to process onboarding message for %s", phone)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process onboarding message",
        )
