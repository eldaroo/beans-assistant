"""
WhatsApp Server Multi-Tenant - Maneja múltiples clientes con bases de datos separadas.

Cada número de teléfono es un cliente diferente con su propia configuración.
"""
import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from whatsapp_client import GreenAPIWhatsAppClient, format_message_for_whatsapp
from graph import create_business_agent_graph
# Audio transcription disabled to reduce Docker image size
# from audio_transcriber import transcribe_audio_from_url
from tenant_manager import get_tenant_manager
from onboarding_agent import (
    get_onboarding_session,
    create_onboarding_session,
    complete_onboarding_session,
    is_in_onboarding
)

# Load environment variables
load_dotenv()

# Green API credentials from environment
ID_INSTANCE = os.getenv("GREEN_API_INSTANCE_ID")
API_TOKEN = os.getenv("GREEN_API_TOKEN")

if not ID_INSTANCE or not API_TOKEN:
    raise ValueError(
        "Missing Green API credentials. Please set GREEN_API_INSTANCE_ID and "
        "GREEN_API_TOKEN in your .env file"
    )

# Initialize tenant manager
tenant_manager = get_tenant_manager()

# Conversation memory: chat_id -> list of messages
conversation_history = {}
MAX_HISTORY = 10  # Keep last 10 messages per user
HISTORY_TIMEOUT = timedelta(hours=2)  # Clear history after 2 hours of inactivity


def extract_phone_number(sender: str) -> str:
    """
    Extract phone number from sender ID.

    Args:
        sender: Sender ID from WhatsApp (e.g., "5491112345678@c.us")

    Returns:
        Phone number with country code (e.g., "+5491112345678")
    """
    # Remove @c.us suffix
    phone = sender.split("@")[0]
    # Add + prefix if not present
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone


def get_conversation_context(chat_id: str) -> str:
    """
    Get formatted conversation history for context.

    Args:
        chat_id: WhatsApp chat ID

    Returns:
        Formatted conversation history as string
    """
    if chat_id not in conversation_history:
        return ""

    history = conversation_history[chat_id]
    if not history:
        return ""

    # Check if history is too old
    last_msg_time = history[-1].get("timestamp")
    if last_msg_time and (datetime.now() - last_msg_time) > HISTORY_TIMEOUT:
        # Clear old history
        conversation_history[chat_id] = []
        return ""

    # Format history
    context_lines = ["Contexto de conversación reciente:"]
    for msg in history[-5:]:  # Only last 5 exchanges
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            context_lines.append(f"Usuario: {content}")
        elif role == "assistant":
            context_lines.append(f"Asistente: {content}")

    return "\n".join(context_lines)


def add_to_history(chat_id: str, role: str, content: str):
    """
    Add message to conversation history.

    Args:
        chat_id: WhatsApp chat ID
        role: 'user' or 'assistant'
        content: Message content
    """
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []

    conversation_history[chat_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now()
    })

    # Keep only last MAX_HISTORY messages
    if len(conversation_history[chat_id]) > MAX_HISTORY:
        conversation_history[chat_id] = conversation_history[chat_id][-MAX_HISTORY:]


def process_onboarding_message(phone_number: str, user_message: str) -> str:
    """
    Process message during onboarding.

    Args:
        phone_number: Client's phone number
        user_message: User's message

    Returns:
        Response message
    """
    session = get_onboarding_session(phone_number)

    if session is None:
        # Start new onboarding
        session = create_onboarding_session(phone_number)
        return session.get_next_message()

    # Process user response
    is_complete, response = session.process_response(user_message)

    if is_complete:
        # Onboarding complete - create tenant
        config = complete_onboarding_session(phone_number)

        if config:
            business_name = config.get("business_name", "Mi Negocio")
            success = tenant_manager.create_tenant(phone_number, business_name, config)

            if success:
                print(f"[TENANT] ✓ New tenant created: {phone_number} ({business_name})")
            else:
                print(f"[TENANT] ✗ Failed to create tenant: {phone_number}")

        return response

    return response


def process_message_with_agent(user_message: str, phone_number: str, chat_id: str = None) -> str:
    """
    Process user message with multi-agent system.

    Args:
        user_message: Message from user
        phone_number: Client's phone number
        chat_id: WhatsApp chat ID for conversation context

    Returns:
        Agent response
    """
    try:
        # Get tenant-specific database path
        db_path = tenant_manager.get_tenant_db_path(phone_number)
        db_uri = f"sqlite:///{db_path}"

        print(f"[TENANT] Using database: {db_path}")

        # Get conversation context
        context = ""
        if chat_id:
            context = get_conversation_context(chat_id)

        # Combine context with current message
        full_input = user_message
        if context:
            full_input = f"{context}\n\nMensaje actual: {user_message}"

        # Create agent graph with tenant-specific DB
        graph = create_business_agent_graph(db_uri)

        # Initial state
        state = {
            "messages": [],
            "user_input": full_input,
            "normalized_entities": {}
        }

        # Run graph
        result = graph.invoke(state)

        # Extract final answer
        final_answer = result.get("final_answer")
        sql_result = result.get("sql_result")

        # Return the most relevant response
        if final_answer:
            return final_answer
        elif sql_result:
            return sql_result
        else:
            return "Lo siento, no pude procesar tu solicitud. ¿Podrías reformularla?"

    except Exception as e:
        # Log the error for debugging
        print(f"\n[ERROR] Agent processing failed: {str(e)}")
        import traceback
        traceback.print_exc()

        # Return user-friendly error messages based on error type
        error_msg = str(e)

        if "No hay suficiente stock" in error_msg:
            return f"⚠️ {error_msg}\n\nPor favor verifica el inventario disponible antes de registrar la venta."
        elif "Unknown product" in error_msg or "no encontrado" in error_msg:
            return f"⚠️ {error_msg}\n\nPor favor verifica que el producto exista en el catálogo."
        elif "duplicate" in error_msg.lower() or "unique constraint" in error_msg.lower():
            return "⚠️ Este elemento ya existe en el sistema. Por favor verifica los datos."
        elif "output parsing error" in error_msg.lower() or "I don't know" in error_msg:
            return "⚠️ No pude entender tu mensaje.\n\nPor favor reformula tu pregunta sobre el negocio (ventas, stock, productos, gastos, ganancias, etc.)"
        else:
            return f"⚠️ Disculpa, hubo un error procesando tu mensaje:\n{error_msg}\n\nPor favor intenta de nuevo o reformula tu pregunta."


def run_whatsapp_server():
    """
    Main server loop - polls for messages and responds.
    """
    print("="*60)
    print("WhatsApp Multi-Tenant Server - Business Assistant")
    print("="*60)
    print(f"Instance ID: {ID_INSTANCE}")
    print("Starting message polling...")
    print("Press Ctrl+C to stop")
    print("="*60)

    # Initialize WhatsApp client
    client = GreenAPIWhatsAppClient(ID_INSTANCE, API_TOKEN)

    # Check instance state
    state = client.get_state_instance()
    print(f"Instance state: {state.get('stateInstance', 'unknown')}")

    if state.get("stateInstance") != "authorized":
        print("\n[WARN] Instance is not authorized!")
        print("Please authorize your WhatsApp instance in Green API console.")
        return

    print("\n[OK] Instance is authorized and ready!")
    print("Waiting for incoming messages...\n")

    # Polling loop
    message_count = 0

    try:
        while True:
            # Poll for new notification
            notification = client.receive_notification()

            if notification:
                # Extract message data
                message_data = client.process_incoming_message(notification)

                if message_data:
                    message_count += 1
                    sender_name = message_data["sender_name"]
                    sender = message_data["sender"]
                    chat_id = message_data["chat_id"]
                    message_type = message_data.get("message_type", "text")
                    user_message = message_data["message"]

                    # Extract phone number
                    phone_number = extract_phone_number(sender)

                    print(f"\n[{message_count}] [MSG] From {sender_name} ({phone_number})")
                    print(f"    [TYPE] {message_type}")

                    # Track timing
                    start_time = time.time()

                    # Handle audio messages
                    if message_type == "audio":
                        print(f"    [AUDIO] Audio message received but transcription is disabled")
                        
                        # Send not-supported message to user
                        client.send_message(
                            chat_id,
                            "Lo siento, actualmente no puedo procesar mensajes de audio. Por favor envía un mensaje de texto."
                        )
                        
                        # Delete notification and continue
                        receipt_id = notification.get("receiptId")
                        if receipt_id:
                            client.delete_notification(receipt_id)
                        continue
                    else:
                        print(f"    [IN] \"{user_message}\"")

                    # Show typing indicator
                    client.send_typing(chat_id)
                    print(f"    [TYPING] Indicator sent")

                    # Check if tenant exists
                    if not tenant_manager.tenant_exists(phone_number):
                        print(f"    [TENANT] New client detected: {phone_number}")
                        print(f"    [TENANT] Starting onboarding process...")

                        # Process onboarding
                        agent_response = process_onboarding_message(phone_number, user_message)

                    elif is_in_onboarding(phone_number):
                        print(f"    [TENANT] Client in onboarding: {phone_number}")

                        # Continue onboarding
                        agent_response = process_onboarding_message(phone_number, user_message)

                    else:
                        print(f"    [TENANT] Existing client: {phone_number}")
                        print(f"    [AGENT] Processing...")

                        # Add user message to history
                        add_to_history(chat_id, "user", user_message)

                        # Process with agent (with conversation context)
                        agent_response = process_message_with_agent(user_message, phone_number, chat_id)

                        # Add assistant response to history
                        add_to_history(chat_id, "assistant", agent_response)

                    process_time = time.time() - start_time
                    print(f"    [AGENT] Processing took {process_time:.2f}s")
                    print(f"    [AGENT] Response: \"{agent_response[:100]}...\"")

                    # Send response
                    send_start = time.time()
                    formatted_response = format_message_for_whatsapp(agent_response)
                    success = client.send_message(chat_id, formatted_response)
                    send_time = time.time() - send_start

                    if success:
                        print(f"    [OUT] Sent in {send_time:.2f}s")
                    else:
                        print(f"    [ERROR] Failed to send response")

                # Delete notification
                receipt_id = notification.get("receiptId")
                if receipt_id:
                    delete_start = time.time()
                    client.delete_notification(receipt_id)
                    delete_time = time.time() - delete_start
                    print(f"    [CLEANUP] Notification deleted in {delete_time:.2f}s")

            # Sleep to avoid hammering the API
            time.sleep(1)  # Poll every 1 second

    except KeyboardInterrupt:
        print("\n\n" + "="*60)
        print(f"Server stopped. Processed {message_count} messages.")
        print("="*60)


if __name__ == "__main__":
    run_whatsapp_server()
