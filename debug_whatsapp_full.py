#!/usr/bin/env python3
"""Full WhatsApp flow debugging with detailed error tracing."""

import sys
import os
import json
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tenant_manager import TenantManager
from backend.services.chat_service import ChatService, ChatTenantNotFoundError
import logging

# Enable detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

TEST_PHONE = "+5491153695627"
TEST_MESSAGE = "Hola, cuántos productos tengo?"

print("\n" + "="*80)
print("FULL WHATSAPP FLOW DEBUG TRACE")
print("="*80)

try:
    print(f"\n[TEST] Phone: {TEST_PHONE}")
    print(f"[TEST] Message: {TEST_MESSAGE}\n")
    
    # Step 1: Tenant validation
    print("[1] TENANT VALIDATION")
    tm = TenantManager()
    normalized = tm.normalize_phone_number(TEST_PHONE)
    print(f"    Normalized: {normalized}")
    
    exists = tm.tenant_exists(normalized)
    print(f"    Exists: {exists}")
    
    if not exists:
        print(f"    ❌ FATAL: Tenant {normalized} does not exist")
        print(f"    Available tenants in registry:")
        with open('configs/tenant_registry.json') as f:
            registry = json.load(f)
            for phone in registry.keys():
                print(f"      - {phone}")
        sys.exit(1)
    
    # Step 2: Database check
    print(f"\n[2] DATABASE CHECK")
    db_path = tm.get_tenant_db_path(normalized)
    print(f"    DB Path: {db_path}")
    db_exists = Path(db_path).exists()
    print(f"    DB Exists: {db_exists}")
    
    if not db_exists:
        print(f"    ❌ FATAL: Database not found at {db_path}")
        sys.exit(1)
    
    # Step 3: Chat service invocation
    print(f"\n[3] CHAT SERVICE INVOCATION")
    try:
        print(f"    Calling ChatService.chat_with_tenant...")
        response, metadata = ChatService.chat_with_tenant(
            phone=TEST_PHONE,
            message=TEST_MESSAGE
        )
        print(f"    ✓ Response received")
        print(f"    Response: {response[:100]}..." if len(response) > 100 else f"    Response: {response}")
        print(f"    Metadata: {json.dumps(metadata, indent=2)}")
        print(f"\n✅ SUCCESS - No errors detected")
        
    except ChatTenantNotFoundError as e:
        print(f"    ❌ ChatTenantNotFoundError: {e}")
        traceback.print_exc()
        sys.exit(1)
        
    except Exception as e:
        print(f"    ❌ {type(e).__name__}: {e}")
        print(f"\nFull traceback:")
        traceback.print_exc()
        
        # Try to extract more info
        print(f"\n[ADDITIONAL DEBUG]")
        print(f"    Exception type: {type(e).__name__}")
        print(f"    Exception args: {e.args}")
        
        sys.exit(1)

except Exception as e:
    print(f"\n❌ UNEXPECTED ERROR: {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*80)
