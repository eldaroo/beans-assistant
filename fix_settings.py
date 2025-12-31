"""
Fix Green API settings to enable incoming webhooks.
"""
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ID_INSTANCE = os.getenv("GREEN_API_INSTANCE_ID")
API_TOKEN = os.getenv("GREEN_API_TOKEN")

if not ID_INSTANCE or not API_TOKEN:
    print("[ERROR] Missing Green API credentials in .env file")
    print("Please set GREEN_API_INSTANCE_ID and GREEN_API_TOKEN")
    exit(1)

BASE_URL = f"https://7105.api.greenapi.com/waInstance{ID_INSTANCE}"

print("="*60)
print("Fixing Green API Settings for HTTP API Polling")
print("="*60)

# Settings to enable for HTTP API polling
settings = {
    "incomingWebhook": "yes",  # CRITICAL: Enable incoming webhooks
    "outgoingWebhook": "yes",   # Enable outgoing message webhooks
    "outgoingMessageWebhook": "yes",  # Enable outgoing message tracking
    "stateWebhook": "yes"  # Enable state changes
}

print("\nUpdating settings...")
print(f"  - incomingWebhook: no → yes (CRITICAL)")
print(f"  - outgoingWebhook: no → yes")
print(f"  - outgoingMessageWebhook: no → yes")
print(f"  - stateWebhook: no → yes")

# Update settings
url = f"{BASE_URL}/setSettings/{API_TOKEN}"

try:
    response = requests.post(url, json=settings, timeout=30)

    if response.status_code == 200:
        result = response.json()
        print("\n[SUCCESS] Settings updated!")
        print(result)

        print("\n" + "="*60)
        print("✅ Configuration fixed!")
        print("="*60)
        print("\nNow you can:")
        print("1. Run: python whatsapp_server.py")
        print("2. Send a WhatsApp message to: +506 6107 1679")
        print("3. The bot will respond automatically!")
        print("="*60)
    else:
        print(f"\n[ERROR] Failed to update settings: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"\n[ERROR] Request failed: {e}")
    import traceback
    traceback.print_exc()
