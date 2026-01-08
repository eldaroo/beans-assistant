"""
Chat Simulation API Endpoint.

Simula mensajes de WhatsApp para testing sin necesidad de enviar mensajes reales.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from graph import create_business_agent_graph

router = APIRouter()


class ChatMessage(BaseModel):
    """Chat message input."""
    phone: str
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "phone": "+5491112345678",
                "message": "cuántos productos tengo?"
            }
        }


class ChatResponse(BaseModel):
    """Chat response output."""
    phone: str
    user_message: str
    bot_response: str
    metadata: dict = {}


@router.post("/chat/simulate", response_model=ChatResponse)
async def simulate_chat(chat: ChatMessage):
    """
    Simula un mensaje de WhatsApp y devuelve la respuesta del bot.

    Útil para testing sin necesidad de enviar mensajes reales por WhatsApp.

    Args:
        chat: Mensaje con phone y message

    Returns:
        Respuesta del bot con metadata

    Example:
        POST /chat/simulate
        {
            "phone": "+5491112345678",
            "message": "cuántos productos tengo?"
        }
    """
    try:
        # Create graph
        graph = create_business_agent_graph()

        # Initial state (same as WhatsApp server)
        initial_state = {
            "messages": [],
            "user_input": chat.message,
            "phone": chat.phone,
            "sender": chat.phone,
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

        # Extract metadata
        metadata = result.get("metadata", {})

        return ChatResponse(
            phone=chat.phone,
            user_message=chat.message,
            bot_response=bot_response,
            metadata=metadata
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {str(e)}"
        )


@router.post("/chat/simulate/batch", response_model=list[ChatResponse])
async def simulate_chat_batch(messages: list[ChatMessage]):
    """
    Simula múltiples mensajes de WhatsApp en secuencia.

    Útil para testing de conversaciones completas.

    Args:
        messages: Lista de mensajes a procesar

    Returns:
        Lista de respuestas del bot

    Example:
        POST /chat/simulate/batch
        [
            {"phone": "+5491112345678", "message": "hola"},
            {"phone": "+5491112345678", "message": "cuántos productos tengo?"},
            {"phone": "+5491112345678", "message": "gracias"}
        ]
    """
    responses = []

    for chat in messages:
        try:
            response = await simulate_chat(chat)
            responses.append(response)
        except Exception as e:
            # Continue processing even if one fails
            responses.append(ChatResponse(
                phone=chat.phone,
                user_message=chat.message,
                bot_response=f"Error: {str(e)}",
                metadata={"error": True}
            ))

    return responses
