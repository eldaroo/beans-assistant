"""
Comprehensive diagnostic script for Green API WhatsApp integration.
Checks all critical settings and provides debugging information.
"""
import os
import requests
import json
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

print("="*70)
print("COMPREHENSIVE GREEN API DIAGNOSTIC")
print("="*70)
print(f"Instance ID: {ID_INSTANCE}")
print("="*70)

# 1. Check instance state
print("\n[1] INSTANCE STATE")
print("-"*70)
try:
    url = f"{BASE_URL}/getStateInstance/{API_TOKEN}"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        state_data = response.json()
        state = state_data.get("stateInstance", "unknown")
        print(f"State: {state}")

        if state == "authorized":
            print("[OK] Instance is authorized")
        elif state == "notAuthorized":
            print("[ERROR] Instance is NOT authorized - need to scan QR code")
        elif state == "blocked":
            print("[ERROR] Instance is BLOCKED - contact Green API support")
        else:
            print(f"[WARN] Unknown state: {state}")
    else:
        print(f"[ERROR] Failed to get state: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"[ERROR] Request failed: {e}")

# 2. Check WhatsApp account info
print("\n[2] WHATSAPP ACCOUNT INFO")
print("-"*70)
try:
    url = f"{BASE_URL}/getWaSettings/{API_TOKEN}"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        wa_settings = response.json()
        print(json.dumps(wa_settings, indent=2))

        # Extract phone number if available
        if "wid" in wa_settings:
            phone = wa_settings["wid"].replace("@c.us", "")
            print(f"\n[IMPORTANT] WhatsApp Phone Number: +{phone}")
            print(f"[IMPORTANT] Send messages to this number: +{phone}")
    else:
        print(f"[ERROR] Failed to get WA settings: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"[ERROR] Request failed: {e}")

# 3. Check instance settings (webhooks, etc.)
print("\n[3] INSTANCE SETTINGS")
print("-"*70)
try:
    url = f"{BASE_URL}/getSettings/{API_TOKEN}"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        settings = response.json()

        # Show critical settings
        incoming = settings.get("incomingWebhook", "unknown")
        outgoing = settings.get("outgoingWebhook", "unknown")
        webhook_url = settings.get("webhookUrl", "")

        print(f"Incoming Webhook: {incoming}")
        print(f"Outgoing Webhook: {outgoing}")
        print(f"Webhook URL: {webhook_url if webhook_url else '(empty - using HTTP API polling)'}")

        if incoming == "yes":
            print("\n[OK] incomingWebhook is ENABLED")
        else:
            print("\n[ERROR] incomingWebhook is DISABLED")
            print("       This prevents message queue from storing incoming messages!")

        # Show all settings
        print("\nAll settings:")
        print(json.dumps(settings, indent=2))
    else:
        print(f"[ERROR] Failed to get settings: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"[ERROR] Request failed: {e}")

# 4. Check for pending notifications
print("\n[4] PENDING NOTIFICATIONS IN QUEUE")
print("-"*70)
try:
    url = f"{BASE_URL}/receiveNotification/{API_TOKEN}"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        notification = response.json()
        if notification and notification.get("receiptId"):
            print("[FOUND] Notification in queue:")
            print(json.dumps(notification, indent=2, ensure_ascii=False))
        else:
            print("[EMPTY] No notifications in queue")
    else:
        print(f"[ERROR] Failed to check notifications: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"[ERROR] Request failed: {e}")

# 5. Check device info
print("\n[5] DEVICE INFO")
print("-"*70)
try:
    url = f"{BASE_URL}/getDeviceInfo/{API_TOKEN}"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        device_info = response.json()
        print(json.dumps(device_info, indent=2))
    else:
        print(f"[WARN] Could not get device info: {response.status_code}")
except Exception as e:
    print(f"[WARN] Request failed: {e}")

# Summary and recommendations
print("\n" + "="*70)
print("SUMMARY AND RECOMMENDATIONS")
print("="*70)

print("\n[CRITICAL CHECKS]")
print("1. Instance State: Check if 'authorized' above")
print("2. Phone Number: Check the phone number shown in section [2]")
print("3. incomingWebhook: Must be 'yes' for HTTP API polling")
print("4. Send a test message to the phone number shown above")

print("\n[TROUBLESHOOTING SINGLE CHECKMARK ISSUE]")
print("If messages show single checkmark (not delivered):")
print("- Verify you're sending to the CORRECT phone number (shown in [2])")
print("- Check if the WhatsApp instance is actually connected")
print("- Try restarting the WhatsApp instance in Green API console")
print("- Check if the account has any restrictions/blocks")
print("- Verify internet connectivity on both sides")

print("\n[NEXT STEPS]")
print("1. Check the phone number in section [2]")
print("2. Send a WhatsApp message to that exact number")
print("3. Wait 10 seconds")
print("4. Run: python debug_messages.py")
print("5. Check if message appears in the queue")

print("="*70)
