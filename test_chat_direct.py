"""
Test directo del endpoint de chat para ver el error exacto
"""
import requests
import json

# Configuracion
BASE_URL = "http://localhost:8000"
TENANT_PHONE = "+541153695627"
TEST_MESSAGE = "hola"

print("=" * 60)
print("TEST DIRECTO DEL ENDPOINT DE CHAT")
print("=" * 60)
print()

# Codificar el telefono
from urllib.parse import quote
encoded_phone = quote(TENANT_PHONE, safe='')

url = f"{BASE_URL}/api/tenants/{encoded_phone}/chat"

print(f"URL: {url}")
print(f"Mensaje: {TEST_MESSAGE}")
print()

try:
    response = requests.post(
        url,
        json={"message": TEST_MESSAGE},
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    
    print(f"Status Code: {response.status_code}")
    print()
    
    if response.status_code == 200:
        data = response.json()
        print("✓ SUCCESS!")
        print()
        print("Response:")
        print(json.dumps(data, indent=2))
    else:
        print("✗ ERROR")
        print()
        print("Response:")
        print(response.text)
        
except requests.exceptions.ConnectionError:
    print("✗ ERROR: No se pudo conectar al backend")
    print("Asegurate de que el backend este corriendo en http://localhost:8000")
except Exception as e:
    print(f"✗ ERROR: {e}")
