"""
Simple test script to verify the chat endpoint works.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

# Test imports
try:
    from backend.api import chat_tenant
    print("✓ chat_tenant module imported successfully")
except Exception as e:
    print(f"✗ Error importing chat_tenant: {e}")
    sys.exit(1)

try:
    from tenant_manager import get_tenant_manager
    print("✓ tenant_manager imported successfully")
except Exception as e:
    print(f"✗ Error importing tenant_manager: {e}")
    sys.exit(1)

try:
    import database
    print("✓ database module imported successfully")
except Exception as e:
    print(f"✗ Error importing database: {e}")
    sys.exit(1)

print("\n✓ All imports successful!")
print("\nTo test the chat endpoint:")
print("1. Start the backend server: python backend/app.py")
print("2. Open http://localhost:8000/tenants/+541153695627")
print("3. Look for the chat widget in the bottom-right corner")
print("4. Click it and try sending a message like 'cuántos productos tengo?'")
