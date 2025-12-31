"""
Debug script to check if messages are being received.
"""
import os
import json
import time
from dotenv import load_dotenv
from whatsapp_client import GreenAPIWhatsAppClient

# Load environment variables
load_dotenv()

ID_INSTANCE = os.getenv("GREEN_API_INSTANCE_ID")
API_TOKEN = os.getenv("GREEN_API_TOKEN")

if not ID_INSTANCE or not API_TOKEN:
    print("[ERROR] Missing Green API credentials in .env file")
    print("Please set GREEN_API_INSTANCE_ID and GREEN_API_TOKEN")
    exit(1)

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
