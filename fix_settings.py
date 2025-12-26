"""
Fix Green API settings to enable incoming webhooks.
"""
import requests

ID_INSTANCE = "7105281616"
API_TOKEN = "e44f5320e85d4222baff6089d5f192bc6363f86e55da4e3e8c"
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
