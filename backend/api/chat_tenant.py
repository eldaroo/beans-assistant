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

# Cache the agent graph to avoid recreating it on every request
# This significantly improves response time
_agent_graph_cache = None

def get_agent_graph():
    """Get cached agent graph or create new one if not exists."""
    global _agent_graph_cache
    if _agent_graph_cache is None:
        _agent_graph_cache = create_business_agent_graph()
    return _agent_graph_cache



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

        # Get cached graph (much faster than creating new one each time)
        graph = get_agent_graph()

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

        # Extract response - need to get the FINAL user-facing message, not router internals
        bot_response = ""
        
        # First, try to get final_answer which is the user-facing response
        if "final_answer" in result and result["final_answer"]:
            bot_response = result["final_answer"]
        
        # If no final_answer, look through messages for user-facing content
        elif "messages" in result and len(result["messages"]) > 0:
            # Filter out internal router/agent messages (those starting with [Router], [Read], etc.)
            user_facing_messages = []
            for msg in result["messages"]:
                content = ""
                if hasattr(msg, 'content'):
                    content = msg.content
                elif isinstance(msg, dict) and 'content' in msg:
                    content = msg['content']
                elif isinstance(msg, str):
                    content = msg
                else:
                    content = str(msg)
                
                # Skip internal agent messages
                if not content.startswith('[Router]') and not content.startswith('[Read]') and \
                   not content.startswith('[Write]') and not content.startswith('[Resolver]'):
                    user_facing_messages.append(content)
            
            # Get the last user-facing message
            if user_facing_messages:
                bot_response = user_facing_messages[-1]
            else:
                # Fallback to last message if no user-facing found
                last_message = result["messages"][-1]
                if hasattr(last_message, 'content'):
                    bot_response = last_message.content
                elif isinstance(last_message, dict) and 'content' in last_message:
                    bot_response = last_message['content']
                elif isinstance(last_message, str):
                    bot_response = last_message
                else:
                    bot_response = str(last_message)

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
