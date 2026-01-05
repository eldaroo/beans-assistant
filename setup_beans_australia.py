"""
Setup script for Beans&Co Australia client.
Phone: +61476777212
"""
from tenant_manager import get_tenant_manager

def setup_beans_australia():
    """Create tenant for Beans&Co Australia."""

    phone_number = "+61476777212"
    business_name = "Beans&Co Australia"

    print("=" * 60)
    print(f"Setting up tenant: {business_name}")
    print(f"Phone number: {phone_number}")
    print("=" * 60)

    # Get tenant manager
    tm = get_tenant_manager()

    # Check if already exists
    if tm.tenant_exists(phone_number):
        print(f"\n[INFO] Tenant already exists!")
        print(f"\nTenant stats:")
        stats = tm.get_tenant_stats(phone_number)
        if stats:
            print(f"  - Products: {stats['products']}")
            print(f"  - Sales: {stats['sales']}")
            print(f"  - Revenue: ${stats['revenue_usd']:.2f}")
            print(f"  - Profit: ${stats['profit_usd']:.2f}")

        config = tm.get_tenant_config(phone_number)
        if config:
            print(f"\nConfig:")
            print(f"  - Business: {config.get('business_name', 'N/A')}")
            print(f"  - Language: {config.get('language', 'N/A')}")
            print(f"  - Currency: {config.get('currency', 'N/A')}")
            print(f"  - Timezone: {config.get('timezone', 'N/A')}")

        return

    # Custom configuration for Australia
    config = {
        "business_name": business_name,
        "phone_number": phone_number,
        "language": "en",  # English for Australia
        "currency": "AUD",  # Australian Dollar
        "timezone": "Australia/Sydney",
        "prompts": {
            "system_prompt": "You are an intelligent business assistant for Beans&Co Australia.",
            "welcome_message": "G'day! I'm your Beans&Co business assistant. How can I help you today?"
        },
        "features": {
            "audio_enabled": True,
            "sales_enabled": True,
            "expenses_enabled": True,
            "inventory_enabled": True
        }
    }

    # Create tenant
    success = tm.create_tenant(
        phone_number=phone_number,
        business_name=business_name,
        config=config
    )

    if success:
        print("\n" + "=" * 60)
        print("[SUCCESS] Tenant created successfully!")
        print("=" * 60)
        print(f"\nTenant info:")
        print(f"  - Phone: {phone_number}")
        print(f"  - Business: {business_name}")
        print(f"  - Database: {tm.get_tenant_db_path(phone_number)}")
        print(f"  - Language: English")
        print(f"  - Currency: AUD")
        print(f"  - Timezone: Australia/Sydney")
        print(f"\nThe tenant is ready to use!")
    else:
        print("\n[ERROR] Failed to create tenant")

if __name__ == "__main__":
    setup_beans_australia()
