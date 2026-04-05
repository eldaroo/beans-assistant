#!/usr/bin/env python3
"""Test backend connectivity and tenant creation."""

import requests
import json
import sys

BACKEND_URL = "http://localhost:8000"  # Adjust if different

def test_backend_health():
    """Test if backend is running."""
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=10)
        print(f"Health check: {response.status_code}")
        if response.status_code == 200:
            print("✓ Backend is running")
            return True
        else:
            print(f"✗ Backend health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Cannot connect to backend: {e}")
        return False

def test_tenant_creation():
    """Test tenant creation endpoint."""
    payload = {
        "phone_number": "+91903727005831",
        "business_name": "Test Tenant India",
        "currency": "USD",
        "language": "es"
    }

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/tenants",
            json=payload,
            timeout=30
        )
        print(f"Tenant creation: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 201:
            print("✓ Tenant created successfully")
            return True
        elif response.status_code == 409:
            print("✓ Tenant already exists")
            return True
        else:
            print(f"✗ Tenant creation failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Cannot create tenant: {e}")
        return False

def test_tenant_chat():
    """Test tenant chat endpoint."""
    payload = {"message": "Hola"}

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/tenants/+91903727005831/chat",
            json=payload,
            timeout=45
        )
        print(f"Tenant chat: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            print("✓ Chat endpoint working")
            return True
        else:
            print(f"✗ Chat endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Cannot access chat endpoint: {e}")
        return False

if __name__ == "__main__":
    print("Testing backend connectivity...")
    print("=" * 50)

    backend_ok = test_backend_health()
    if not backend_ok:
        print("\n❌ Backend is not accessible. Check if it's running.")
        sys.exit(1)

    print("\nTesting tenant creation...")
    tenant_ok = test_tenant_creation()

    print("\nTesting tenant chat...")
    chat_ok = test_tenant_chat()

    print("\n" + "=" * 50)
    if tenant_ok and chat_ok:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
        sys.exit(1)