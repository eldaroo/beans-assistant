"""
Debug script to check if messages are being received.
"""
from whatsapp_client import GreenAPIWhatsAppClient
import json
import time

ID_INSTANCE = "7105281616"
API_TOKEN = "e44f5320e85d4222baff6089d5f192bc6363f86e55da4e3e8c"

client = GreenAPIWhatsAppClient(ID_INSTANCE, API_TOKEN)

print("="*60)
print("Checking for incoming messages...")
print("="*60)

# Try to receive notification multiple times
for i in range(5):
    print(f"\n[Attempt {i+1}/5] Polling for notifications...")

    notification = client.receive_notification()

    if notification:
        print("\n[FOUND] Notification received!")
        print(json.dumps(notification, indent=2, ensure_ascii=False))

        # Try to process as message
        message_data = client.process_incoming_message(notification)
        if message_data:
            print("\n[MESSAGE] Incoming message detected:")
            print(f"  From: {message_data['sender_name']}")
            print(f"  Sender: {message_data['sender']}")
            print(f"  Chat ID: {message_data['chat_id']}")
            print(f"  Message: {message_data['message']}")
        else:
            print("\n[INFO] Notification is not a text message")

        # Ask if should delete
        print("\nDo you want to delete this notification? (y/n)")
        # For now, don't delete automatically
        break
    else:
        print("  No notifications in queue")

    time.sleep(2)

print("\n" + "="*60)
print("Debug completed")
print("="*60)
