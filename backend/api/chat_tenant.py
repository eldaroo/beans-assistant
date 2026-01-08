"""
Chat API Endpoint for Tenant-Specific Conversations.

Allows users to chat with the AI agent in the context of a specific tenant's database.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from graph import create_business_agent_graph
from tenant_manager import get_tenant_manager
import database

router = APIRouter()


class TenantChatMessage(BaseModel):
    """Chat message input for tenant-specific chat."""
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "message": "cuántos productos tengo?"
            }
        }


class TenantChatResponse(BaseModel):
    """Chat response output."""
    response: str
    metadata: dict = {}


@router.post("/{phone}/chat", response_model=TenantChatResponse)
async def chat_with_tenant(phone: str, chat: TenantChatMessage):
    """
    Chat with the AI agent in the context of a specific tenant's database.

    This endpoint allows users to interact with the multi-agent system
    while automatically scoping all operations to the specified tenant's database.

    Args:
        phone: Tenant phone number (e.g., "+5491112345678")
        chat: Message to send to the agent

    Returns:
        Agent's response with metadata

    Example:
        POST /api/tenants/+5491112345678/chat
        {
            "message": "cuántos productos tengo?"
        }

        Response:
        {
            "response": "Tenés 15 productos activos...",
            "metadata": {
                "intent": "READ_ANALYTICS",
                "confidence": 0.95
            }
        }
    """
    try:
        # Verify tenant exists
        tenant_manager = get_tenant_manager()
        if not tenant_manager.tenant_exists(phone):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {phone} not found"
            )

        # Get tenant database path
        db_path = tenant_manager.get_tenant_db_path(phone)
        
        # Set the database path for this request
        # This ensures all database operations use the correct tenant's database
        database.DB_PATH = db_path

        # Create graph
        graph = create_business_agent_graph()

        # Initial state (similar to WhatsApp server)
        initial_state = {
            "messages": [],
            "user_input": chat.message,
            "phone": phone,
            "sender": phone,
            "normalized_entities": {},
            "metadata": {}
        }

        # Invoke graph
        result = graph.invoke(initial_state)

        # Extract response
        bot_response = ""
        if "messages" in result and len(result["messages"]) > 0:
            last_message = result["messages"][-1]

            # Handle different message formats
            if hasattr(last_message, 'content'):
                bot_response = last_message.content
            elif isinstance(last_message, dict) and 'content' in last_message:
                bot_response = last_message['content']
            elif isinstance(last_message, str):
                bot_response = last_message
            else:
                bot_response = str(last_message)

        # If no message in messages array, try final_answer
        if not bot_response and "final_answer" in result:
            bot_response = result["final_answer"]

        # Extract metadata
        metadata = {
            "intent": result.get("intent"),
            "operation_type": result.get("operation_type"),
            "confidence": result.get("confidence"),
        }

        return TenantChatResponse(
            response=bot_response,
            metadata=metadata
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        import traceback
        print(f"[CHAT] Error processing message: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {str(e)}"
        )
