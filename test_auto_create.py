#!/usr/bin/env python3
"""Test auto-tenant creation from backend."""

import requests
import json
import sys

BACKEND_URL = "http://localhost:8000"  # Adjust if different

def test_auto_create_flow():
    """Test the complete auto-create flow."""
    test_phone = "+91903727005831"

    print("Testing auto-tenant creation flow...")
    print("=" * 50)

    # Step 1: Try chat with non-existent tenant (should fail with 404)
    print(f"1. Testing chat with non-existent tenant {test_phone}...")
    chat_payload = {"message": "Hola"}

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/tenants/{test_phone}/chat",
            json=chat_payload,
            timeout=45
        )
        print(f"   Chat response: {response.status_code}")
        if response.status_code == 404:
            print("   ✅ Got expected 404 for non-existent tenant")
        else:
            print(f"   ❌ Unexpected status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

    # Step 2: Create tenant manually
    print(f"\n2. Creating tenant {test_phone} manually...")
    create_payload = {
        "phone_number": test_phone,
        "business_name": f"Tenant {test_phone}",
        "currency": "USD",
        "language": "es"
    }

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/tenants",
            json=create_payload,
            timeout=30
        )
        print(f"   Create response: {response.status_code}")
        print(f"   Response: {response.text}")

        if response.status_code in [201, 409]:  # Created or already exists
            print("   ✅ Tenant created/exists")
        else:
            print(f"   ❌ Failed to create tenant: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Error creating tenant: {e}")
        return False

    # Step 3: Try chat again (should work now)
    print(f"\n3. Testing chat with existing tenant {test_phone}...")
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/tenants/{test_phone}/chat",
            json=chat_payload,
            timeout=45
        )
        print(f"   Chat response: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ Chat working after tenant creation")
            data = response.json()
            print(f"   Response: {data.get('response', '')[:100]}...")
            return True
        else:
            print(f"   ❌ Chat still failing: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_auto_create_flow()
    print("\n" + "=" * 50)
    if success:
        print("✅ Auto-create flow test PASSED")
    else:
        print("❌ Auto-create flow test FAILED")
    sys.exit(0 if success else 1)