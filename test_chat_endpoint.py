"""
Test the chat endpoint directly to see what's happening.
"""
import requests
from urllib.parse import quote

# Configuration
BASE_URL = "http://localhost:8000"
TENANT_PHONE = "+541153695627"  # Change this to your tenant phone

def test_endpoint():
    print("=" * 60)
    print("TESTING CHAT ENDPOINT")
    print("=" * 60)
    
    # Test 1: Check if backend is running
    print("\n[1/3] Checking if backend is running...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        print(f"✓ Backend is running (status: {response.status_code})")
    except requests.exceptions.ConnectionError:
        print("✗ Backend is NOT running")
        print("\nStart it with: python backend/app.py")
        return
    
    # Test 2: Check available routes
    print("\n[2/3] Checking API docs...")
    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=2)
        print(f"✓ API docs available at {BASE_URL}/docs")
        print("  Open this in your browser to see all available endpoints")
    except:
        print("⚠ Could not access API docs")
    
    # Test 3: Test chat endpoint
    print(f"\n[3/3] Testing chat endpoint with tenant: {TENANT_PHONE}")
    
    # Try different URL encodings
    encodings = {
        "encodeURIComponent": quote(TENANT_PHONE, safe=''),
        "quote with safe=/": quote(TENANT_PHONE, safe='/'),
        "no encoding": TENANT_PHONE
    }
    
    for encoding_name, encoded_phone in encodings.items():
        url = f"{BASE_URL}/api/tenants/{encoded_phone}/chat"
        print(f"\n  Testing with {encoding_name}:")
        print(f"    URL: {url}")
        
        try:
            response = requests.post(
                url,
                json={"message": "hola"},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            print(f"    Status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"    ✓ SUCCESS!")
                data = response.json()
                print(f"    Response: {data.get('response', 'No response')[:100]}...")
                break
            elif response.status_code == 404:
                print(f"    ✗ 404 Not Found")
                print(f"    Response: {response.text[:200]}")
            else:
                print(f"    ✗ Error: {response.status_code}")
                print(f"    Response: {response.text[:200]}")
        except Exception as e:
            print(f"    ✗ Exception: {e}")
    
    # Test 4: List all tenants
    print("\n[4/4] Checking available tenants...")
    try:
        response = requests.get(f"{BASE_URL}/api/tenants", timeout=2)
        if response.status_code == 200:
            tenants = response.json()
            if tenants:
                print(f"✓ Found {len(tenants)} tenant(s):")
                for tenant in tenants:
                    phone = tenant.get('phone_number', 'Unknown')
                    name = tenant.get('business_name', 'Unknown')
                    print(f"  - {phone}: {name}")
            else:
                print("⚠ No tenants found")
        else:
            print(f"⚠ Could not list tenants (status: {response.status_code})")
    except Exception as e:
        print(f"⚠ Error listing tenants: {e}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    
    print("\nNext steps:")
    print("1. Make sure backend is running: python backend/app.py")
    print("2. Check the URL in browser console matches the working URL above")
    print("3. Refresh browser with Ctrl+F5 to reload JavaScript")
    print(f"4. Open browser console and look for [Chat Widget] logs")

if __name__ == "__main__":
    test_endpoint()
