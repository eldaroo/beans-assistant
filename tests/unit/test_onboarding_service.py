from onboarding_agent import complete_onboarding_session

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


class _FakeProductsService:
    def __init__(self):
        self.created_products = []

    def create_product(self, phone, payload):
        self.created_products.append(
            {
                "phone": phone,
                "sku": payload.sku,
                "name": payload.name,
                "unit_cost_cents": payload.unit_cost_cents,
                "unit_price_cents": payload.unit_price_cents,
            }
        )
        return payload


def test_onboarding_service_starts_with_text_welcome():
    phone = "+5491112345678"
    complete_onboarding_session(phone)
    fake_tenants_service = _FakeTenantsService()
    fake_products_service = _FakeProductsService()
    service = OnboardingService(fake_tenants_service, fake_products_service)

    result = service.handle_message(phone, "hola")
    assert result["metadata"]["onboarding_complete"] is False
    assert result["metadata"]["step"] == "welcome"
    assert result["metadata"]["phase"] == "setup"
    assert result["metadata"]["product_created"] is False
    assert "bienvenido" in result["response"].lower()
    assert "responde *si* para empezar" in result["response"].lower()
    assert result["messages"][0]["type"] == "text"
    assert "responde *si* para empezar" in result["messages"][0]["text"].lower()
    assert fake_tenants_service.created_tenants == []
    assert fake_products_service.created_products == []


def test_onboarding_service_creates_tenant_and_first_product(monkeypatch):
    phone = "+5491112345678"
    complete_onboarding_session(phone)
    fake_tenants_service = _FakeTenantsService()
    fake_products_service = _FakeProductsService()
    service = OnboardingService(fake_tenants_service, fake_products_service)

    from contextlib import contextmanager

    @contextmanager
    def _tenant_scope(_phone):
        yield

    monkeypatch.setattr("backend.services.onboarding_service.tenant_scope", _tenant_scope)

    result = service.handle_message(phone, "hola")
    assert result["metadata"]["step"] == "welcome"

    result = service.handle_message(phone, "Si")
    assert "tu nombre" in result["response"].lower()

    result = service.handle_message(phone, "Sofia")
    assert "nombre de tu negocio" in result["response"].lower()

    result = service.handle_message(phone, "Mi tienda")
    assert "moneda" in result["response"].lower()

    result = service.handle_message(phone, "ARS")
    assert "queda asi" in result["response"].lower()

    result = service.handle_message(phone, "Si")
    assert result["metadata"]["onboarding_complete"] is False
    assert "deseas agregar un producto a tu inventario" in result["response"].lower()

    result = service.handle_message(phone, "Pulsera coral")
    assert "precio" in result["response"].lower()

    result = service.handle_message(phone, "25000")
    assert result["metadata"]["onboarding_complete"] is True
    assert result["metadata"]["tenant_created"] is True
    assert result["metadata"]["product_created"] is True
    assert "cargar stock" in result["response"].lower()
    assert "ej: *agrega 10 unidades de pulsera coral*" in result["response"].lower()
    assert "cuando cargues stock, tambien vas a poder" in result["response"].lower()
    assert "ej: *vendi 2 pulsera coral*" in result["response"].lower()
    assert "ej: *mostrame mi catalogo*" in result["response"].lower()

    assert len(fake_tenants_service.created_tenants) == 1
    created = fake_tenants_service.created_tenants[0]
    assert created["phone_number"] == phone
    assert created["business_name"] == "Mi tienda"
    assert created["owner_name"] == "Sofia"
    assert created["currency"] == "ARS"
    assert created["language"] == "es"
    assert "first_goal" not in created["extra_config"]
    assert "business_type" not in created["extra_config"]
    assert created["extra_config"]["first_product_name"] == "Pulsera coral"
    assert created["extra_config"]["first_product_cost_cents"] == 0

    assert len(fake_products_service.created_products) == 1
    created_product = fake_products_service.created_products[0]
    assert created_product["phone"] == phone
    assert created_product["name"] == "Pulsera coral"
    assert created_product["sku"] == "PULSERA-CORAL"
    assert created_product["unit_cost_cents"] == 0
    assert created_product["unit_price_cents"] == 2500000


def test_onboarding_service_normalizes_conversational_product_name(monkeypatch):
    phone = "+5491112345679"
    complete_onboarding_session(phone)
    fake_tenants_service = _FakeTenantsService()
    fake_products_service = _FakeProductsService()
    service = OnboardingService(fake_tenants_service, fake_products_service)

    from contextlib import contextmanager

    @contextmanager
    def _tenant_scope(_phone):
        yield

    monkeypatch.setattr("backend.services.onboarding_service.tenant_scope", _tenant_scope)

    service.handle_message(phone, "hola")
    service.handle_message(phone, "Si")
    service.handle_message(phone, "Sofia")
    service.handle_message(phone, "Mi tienda")
    service.handle_message(phone, "ARS")
    service.handle_message(phone, "Si")

    result = service.handle_message(phone, "Vendo medias")
    assert "precio de venta" in result["response"].lower()

    service.handle_message(phone, "24000")

    created_product = fake_products_service.created_products[0]
    assert created_product["name"] == "medias"
    assert created_product["sku"] == "MEDIAS"
    assert created_product["unit_cost_cents"] == 0
