"""
Test WhatsApp integration with Green API.

Verifies connection and basic functionality.
"""
from whatsapp_client import GreenAPIWhatsAppClient


def test_green_api_connection():
    """Test connection to Green API."""
    print("="*60)
    print("Testing Green API WhatsApp Integration")
    print("="*60)

    # Initialize client
    ID_INSTANCE = "7105281616"
    API_TOKEN = "e44f5320e85d4222baff6089d5f192bc6363f86e55da4e3e8c"

    client = GreenAPIWhatsAppClient(ID_INSTANCE, API_TOKEN)

    # Test 1: Get instance state
    print("\n[Test 1] Getting instance state...")
    state = client.get_state_instance()

    if state:
        state_instance = state.get("stateInstance", "unknown")
        print(f"  [OK] Instance state: {state_instance}")

        if state_instance == "authorized":
            print(f"  [OK] Instance is authorized and ready!")
        elif state_instance == "notAuthorized":
            print(f"  [WARN] Instance is NOT authorized. Please scan QR code in Green API console.")
        elif state_instance == "blocked":
            print(f"  [ERROR] Instance is BLOCKED. Contact Green API support.")
        else:
            print(f"  [WARN] Unknown state: {state_instance}")
    else:
        print(f"  [ERROR] Failed to get instance state")
        return False

    # Test 2: Check for notifications
    print("\n[Test 2] Checking for pending notifications...")
    notification = client.receive_notification()

    if notification:
        print(f"  [OK] Found notification:")
        print(f"    Receipt ID: {notification.get('receiptId')}")
        print(f"    Body: {notification.get('body', {})}")

        # Process if it's a message
        message_data = client.process_incoming_message(notification)
        if message_data:
            print(f"  [OK] Incoming message detected:")
            print(f"    From: {message_data['sender_name']} ({message_data['sender']})")
            print(f"    Message: \"{message_data['message']}\"")

        # Don't delete it for now (leave it for the server)
    else:
        print(f"  [OK] No pending notifications (queue is empty)")

    print("\n" + "="*60)
    print("[SUCCESS] Connection test completed successfully!")
    print("="*60)
    print("\nNext steps:")
    print("1. If instance is authorized, run: python whatsapp_server.py")
    print("2. Send a WhatsApp message to your instance")
    print("3. Watch the server process and respond!")
    print("="*60)

    return True


if __name__ == "__main__":
    test_green_api_connection()
