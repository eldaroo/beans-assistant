"""
Script de prueba para el sistema multi-tenant.
"""
from tenant_manager import get_tenant_manager
from onboarding_agent import create_onboarding_session, process_onboarding_message


def test_tenant_creation():
    """Test creating tenants manually."""
    print("="*60)
    print("TEST: Manual Tenant Creation")
    print("="*60)

    tm = get_tenant_manager()

    # Create test tenant
    success = tm.create_tenant(
        phone_number="+5491112345678",
        business_name="Beans&Co Test",
        config={
            "business_type": "Pulseras artesanales",
            "currency": "USD"
        }
    )

    if success:
        print("✓ Tenant created successfully")

        # Get tenant stats
        stats = tm.get_tenant_stats("+5491112345678")
        print(f"\nStats: {stats}")

        # Get config
        config = tm.get_tenant_config("+5491112345678")
        print(f"\nConfig: {config['business_name']}")
        print(f"Currency: {config['currency']}")

    else:
        print("✗ Tenant already exists")


def test_onboarding_flow():
    """Test the onboarding conversation flow."""
    print("\n" + "="*60)
    print("TEST: Onboarding Flow")
    print("="*60)

    phone = "+5491187654321"

    # Simulate onboarding conversation
    messages = [
        "Hola",  # Welcome
        "Sí",    # Start onboarding
        "Tienda de María",  # Business name
        "Vendo ropa",  # Business type
        "ARS",  # Currency
        "No",  # Add products now?
        "Sí",  # Confirm
    ]

    print("\nSimulating onboarding conversation...")
    print("-"*60)

    for msg in messages:
        response = process_onboarding_message(phone, msg)
        print(f"\nUser: {msg}")
        print(f"Bot: {response[:200]}...")

    # Check if tenant was created
    tm = get_tenant_manager()
    if tm.tenant_exists(phone):
        print("\n✓ Tenant created through onboarding!")
        config = tm.get_tenant_config(phone)
        print(f"  Business: {config['business_name']}")
        print(f"  Currency: {config['currency']}")
    else:
        print("\n✗ Tenant not created")


def test_list_tenants():
    """Test listing all tenants."""
    print("\n" + "="*60)
    print("TEST: List All Tenants")
    print("="*60)

    tm = get_tenant_manager()
    tenants = tm.list_tenants()

    print(f"\nTotal tenants: {len(tenants)}")
    print("-"*60)

    for phone, info in tenants.items():
        print(f"\n{phone}:")
        print(f"  Business: {info['business_name']}")
        print(f"  Created: {info['created_at']}")
        print(f"  Status: {info['status']}")

        # Get stats
        stats = tm.get_tenant_stats(phone)
        if stats:
            print(f"  Products: {stats['products']}")
            print(f"  Sales: {stats['sales']}")
            print(f"  Revenue: ${stats['revenue_usd']:.2f}")
            print(f"  Profit: ${stats['profit_usd']:.2f}")


if __name__ == "__main__":
    import sys

    print("Multi-Tenant System Test")
    print("="*60)

    if len(sys.argv) > 1:
        if sys.argv[1] == "create":
            test_tenant_creation()
        elif sys.argv[1] == "onboarding":
            test_onboarding_flow()
        elif sys.argv[1] == "list":
            test_list_tenants()
        else:
            print("Usage: python test_multitenant.py [create|onboarding|list]")
    else:
        # Run all tests
        test_tenant_creation()
        test_onboarding_flow()
        test_list_tenants()

    print("\n" + "="*60)
    print("Tests complete!")
    print("="*60)
