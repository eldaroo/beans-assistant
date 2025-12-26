"""
Check Green API account settings and information.
"""
from whatsapp_client import GreenAPIWhatsAppClient
import json

ID_INSTANCE = "7105281616"
API_TOKEN = "e44f5320e85d4222baff6089d5f192bc6363f86e55da4e3e8c"

client = GreenAPIWhatsAppClient(ID_INSTANCE, API_TOKEN)

print("="*60)
print("Green API Account Information")
print("="*60)

# Get state
print("\n[1] Instance State:")
state = client.get_state_instance()
print(json.dumps(state, indent=2))

# Get settings
print("\n[2] Instance Settings:")
settings_url = f"{client.base_url}/getSettings/{client.api_token}"
import requests
try:
    response = requests.get(settings_url)
    if response.status_code == 200:
        settings = response.json()
        print(json.dumps(settings, indent=2))
    else:
        print(f"Error: {response.status_code}")
except Exception as e:
    print(f"Error: {e}")

# Get account info
print("\n[3] WAAccount Info:")
wamid_url = f"{client.base_url}/getWaSettings/{client.api_token}"
try:
    response = requests.get(wamid_url)
    if response.status_code == 200:
        wa_settings = response.json()
        print(json.dumps(wa_settings, indent=2))
    else:
        print(f"Error: {response.status_code}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "="*60)
print("IMPORTANT: Para recibir mensajes, asegúrate de que:")
print("1. webhookUrl esté vacío (usamos HTTP API polling)")
print("2. incomingWebhook esté en 'yes' (habilitado)")
print("="*60)
