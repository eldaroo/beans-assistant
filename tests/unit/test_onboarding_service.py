from backend.services.onboarding_service import OnboardingService


class _FakeTenantManager:
    def __init__(self):
        self.created = []

    def normalize_phone_number(self, phone: str) -> str:
        return phone

    def tenant_exists(self, phone: str) -> bool:
        return False

    def get_tenant_config(self, phone: str) -> dict:
        return {}


class _FakeRepository:
    def __init__(self):
        self.tenant_manager = _FakeTenantManager()


class _FakeTenantsService:
    def __init__(self):
        self.repository = _FakeRepository()
        self.created_tenants = []

    def create_tenant(self, payload, extra_config=None):
        self.created_tenants.append(
            {
                "phone_number": payload.phone_number,
                "business_name": payload.business_name,
                "owner_name": payload.owner_name,
                "currency": payload.currency,
                "language": payload.language,
                "extra_config": extra_config or {},
            }
        )


def test_onboarding_service_creates_tenant_at_completion():
    fake_tenants_service = _FakeTenantsService()
    service = OnboardingService(fake_tenants_service)
    phone = "+5491112345678"

    result = service.handle_message(phone, "hola")
    assert result["metadata"]["onboarding_complete"] is False
    assert "como te llamas" in result["response"].lower()

    result = service.handle_message(phone, "Sofia")
    assert "como se llama tu negocio" in result["response"].lower()

    result = service.handle_message(phone, "Mi tienda")
    assert "moneda" in result["response"].lower()

    result = service.handle_message(phone, "ARS")
    assert "resumen de tu configuracion" in result["response"].lower()

    result = service.handle_message(phone, "Si")
    assert result["metadata"]["onboarding_complete"] is True
    assert result["metadata"]["tenant_created"] is True
    assert "ya quedo configurado" in result["response"].lower()

    assert len(fake_tenants_service.created_tenants) == 1
    created = fake_tenants_service.created_tenants[0]
    assert created["phone_number"] == phone
    assert created["business_name"] == "Mi tienda"
    assert created["owner_name"] == "Sofia"
    assert created["currency"] == "ARS"
    assert created["language"] == "es"
    assert "first_goal" not in created["extra_config"]
    assert "business_type" not in created["extra_config"]
