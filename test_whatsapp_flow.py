#!/usr/bin/env python3
"""Test the complete WhatsApp → Backend flow with detailed diagnostics."""

import json
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tenant_manager import TenantManager
from backend.services.chat_service import ChatService
from database_config import TenantContext

# Test phone
TEST_PHONE = "+5491153695627"

print("\n" + "="*60)
print("WHATSAPP TENANT CHAT FLOW DIAGNOSTIC")
print("="*60)

# Step 1: Check if tenant exists
print(f"\n[1] Checking if tenant exists: {TEST_PHONE}")
tm = TenantManager()
normalized = tm.normalize_phone_number(TEST_PHONE)
print(f"    Normalized phone: {normalized}")
print(f"    Tenant exists: {tm.tenant_exists(normalized)}")

if not tm.tenant_exists(normalized):
    print(f"    ❌ FAILED: Normalized phone {normalized} does not exist as tenant")
    print(f"    Available tenants:")
    import json
    with open('configs/tenant_registry.json') as f:
        registry = json.load(f)
        for phone in registry.keys():
            print(f"      - {phone}")
    sys.exit(1)

print(f"    ✓ Tenant exists")

# Step 2: Check tenant database path
print(f"\n[2] Checking tenant database path")
db_path = tm.get_tenant_db_path(normalized)
print(f"    DB Path: {db_path}")
print(f"    DB exists: {Path(db_path).exists()}")

if not Path(db_path).exists():
    print(f"    ❌ FAILED: Database file not found at {db_path}")
    sys.exit(1)

print(f"    ✓ Database exists")

# Step 3: Try chat_with_tenant directly
print(f"\n[3] Testing ChatService.chat_with_tenant directly")
try:
    response, metadata = ChatService.chat_with_tenant(
        phone=TEST_PHONE,
        message="Hola, ¿cuántos productos tengo?"
    )
    print(f"    Response: {response}")
    print(f"    Metadata: {metadata}")
    print(f"    ✓ ChatService succeeded")
except Exception as e:
    print(f"    ❌ FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*60)
print("✓ ALL CHECKS PASSED")
print("="*60 + "\n")
