"""
Diagnostic script for chat widget issues.
Run this to identify problems with the chat endpoint.
"""
import sys
from pathlib import Path

print("=" * 60)
print("CHAT WIDGET DIAGNOSTIC")
print("=" * 60)

# Test 1: Check imports
print("\n[1/5] Checking imports...")
try:
    sys.path.append(str(Path(__file__).parent))
    from backend.api import chat_tenant
    print("✓ chat_tenant module imported")
except Exception as e:
    print(f"✗ Error importing chat_tenant: {e}")
    print("\nPossible fixes:")
    print("- Install dependencies: pip install -r requirements.txt")
    print("- Check that backend/api/chat_tenant.py exists")
    sys.exit(1)

try:
    from tenant_manager import get_tenant_manager
    print("✓ tenant_manager imported")
except Exception as e:
    print(f"✗ Error importing tenant_manager: {e}")
    sys.exit(1)

try:
    from graph import create_business_agent_graph
    print("✓ graph module imported")
except Exception as e:
    print(f"✗ Error importing graph: {e}")
    print("\nPossible fixes:")
    print("- Install langchain: pip install langchain langchain-google-genai langgraph")
    print("- Set GOOGLE_API_KEY in .env")
    sys.exit(1)

# Test 2: Check environment
print("\n[2/5] Checking environment...")
import os
from dotenv import load_dotenv
load_dotenv()

google_key = os.getenv("GOOGLE_API_KEY")
if google_key:
    print(f"✓ GOOGLE_API_KEY is set ({google_key[:10]}...)")
else:
    print("✗ GOOGLE_API_KEY not set")
    print("\nFix: Add GOOGLE_API_KEY to your .env file")

# Test 3: Check tenants
print("\n[3/5] Checking tenants...")
try:
    tenant_manager = get_tenant_manager()
    tenants = tenant_manager.list_tenants()
    if tenants:
        print(f"✓ Found {len(tenants)} tenant(s):")
        for tenant in tenants:
            print(f"  - {tenant['phone_number']}: {tenant.get('business_name', 'Unknown')}")
    else:
        print("✗ No tenants found")
        print("\nFix: Create a tenant first")
except Exception as e:
    print(f"✗ Error loading tenants: {e}")

# Test 4: Check database
print("\n[4/5] Checking database...")
try:
    import database
    print(f"✓ Database module loaded (DB_PATH: {getattr(database, 'DB_PATH', 'Not set')})")
except Exception as e:
    print(f"✗ Error loading database: {e}")

# Test 5: Test endpoint (if backend is running)
print("\n[5/5] Testing chat endpoint...")
try:
    import requests
    
    # Try to connect to backend
    try:
        response = requests.get("http://localhost:8000/health", timeout=2)
        print(f"✓ Backend is running (status: {response.status_code})")
    except requests.exceptions.ConnectionError:
        print("✗ Backend is NOT running")
        print("\nFix: Start the backend with: python backend/app.py")
        sys.exit(0)
    
    # Test chat endpoint
    if tenants:
        test_phone = tenants[0]['phone_number']
        print(f"\nTesting chat with tenant: {test_phone}")
        
        from urllib.parse import quote
        encoded_phone = quote(test_phone, safe='')
        url = f"http://localhost:8000/api/tenants/{encoded_phone}/chat"
        
        try:
            response = requests.post(
                url,
                json={"message": "hola"},
                timeout=10
            )
            
            if response.status_code == 200:
                print("✓ Chat endpoint works!")
                data = response.json()
                print(f"  Response: {data.get('response', 'No response')[:100]}...")
            else:
                print(f"✗ Chat endpoint returned {response.status_code}")
                print(f"  Error: {response.text}")
        except Exception as e:
            print(f"✗ Error calling chat endpoint: {e}")
    
except ImportError:
    print("⚠ requests module not installed (skipping endpoint test)")
    print("  Install with: pip install requests")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)

print("\nCommon issues and fixes:")
print("1. Backend not running → python backend/app.py")
print("2. Missing dependencies → pip install -r requirements.txt")
print("3. No GOOGLE_API_KEY → Add to .env file")
print("4. No tenants → Create a tenant first")
print("5. 404 error → Refresh browser (Ctrl+F5) to reload JavaScript")
