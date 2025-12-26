"""
WhatsApp Server - Integrates multi-agent system with WhatsApp via Green API.

Polls for incoming WhatsApp messages and processes them with the agent system.
"""
import time
from datetime import datetime, timedelta
from whatsapp_client import GreenAPIWhatsAppClient, format_message_for_whatsapp
from graph import create_business_agent_graph


# Green API credentials
ID_INSTANCE = "7105281616"
API_TOKEN = "e44f5320e85d4222baff6089d5f192bc6363f86e55da4e3e8c"

# Conversation memory: chat_id -> list of messages
conversation_history = {}
MAX_HISTORY = 10  # Keep last 10 messages per user
HISTORY_TIMEOUT = timedelta(hours=2)  # Clear history after 2 hours of inactivity


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


def process_message_with_agent(user_message: str, chat_id: str = None) -> str:
    """
    Process user message with multi-agent system.

    Args:
        user_message: Message from user
        chat_id: WhatsApp chat ID for conversation context

    Returns:
        Agent response
    """
    try:
        # Get conversation context
        context = ""
        if chat_id:
            context = get_conversation_context(chat_id)

        # Combine context with current message
        full_input = user_message
        if context:
            full_input = f"{context}\n\nMensaje actual: {user_message}"

        # Create agent graph
        graph = create_business_agent_graph()

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
        print(f"Error processing message: {e}")
        import traceback
        traceback.print_exc()
        return f"Disculpa, hubo un error procesando tu mensaje. Por favor intenta de nuevo."


def run_whatsapp_server():
    """
    Main server loop - polls for messages and responds.
    """
    print("="*60)
    print("WhatsApp Server - Beans&Co Business Assistant")
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
                    user_message = message_data["message"]

                    print(f"\n[{message_count}] [MSG] From {sender_name} ({sender})")
                    print(f"    [IN] \"{user_message}\"")

                    # Track timing
                    import time as time_module
                    start_time = time_module.time()

                    print(f"    [AGENT] Processing...")

                    # Add user message to history
                    add_to_history(chat_id, "user", user_message)

                    # Process with agent (with conversation context)
                    agent_response = process_message_with_agent(user_message, chat_id)

                    # Add assistant response to history
                    add_to_history(chat_id, "assistant", agent_response)

                    process_time = time_module.time() - start_time
                    print(f"    [AGENT] Processing took {process_time:.2f}s")
                    print(f"    [AGENT] Response: \"{agent_response[:100]}...\"")

                    # Send response
                    send_start = time_module.time()
                    formatted_response = format_message_for_whatsapp(agent_response)
                    success = client.send_message(chat_id, formatted_response)
                    send_time = time_module.time() - send_start

                    if success:
                        print(f"    [OUT] Sent in {send_time:.2f}s")
                    else:
                        print(f"    [ERROR] Failed to send response")

                # Delete notification
                receipt_id = notification.get("receiptId")
                if receipt_id:
                    delete_start = time_module.time()
                    client.delete_notification(receipt_id)
                    delete_time = time_module.time() - delete_start
                    print(f"    [CLEANUP] Notification deleted in {delete_time:.2f}s")

            # Sleep to avoid hammering the API (reduced to 1 second for faster response)
            time.sleep(1)  # Poll every 1 second

    except KeyboardInterrupt:
        print("\n\n" + "="*60)
        print(f"Server stopped. Processed {message_count} messages.")
        print("="*60)


if __name__ == "__main__":
    run_whatsapp_server()
