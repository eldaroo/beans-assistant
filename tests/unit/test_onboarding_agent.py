from onboarding_agent import (
    OnboardingSession,
    complete_onboarding_session,
    create_onboarding_session,
    is_in_onboarding,
)


def test_onboarding_requires_explicit_confirmation_before_advancing():
    phone = "+5491112345678"
    session = create_onboarding_session(phone)

    assert is_in_onboarding(phone)
    assert "bienvenido" in session.get_next_message().lower()
    assert "responde *si* para empezar" in session.get_next_message().lower()

    complete, next_payload = session.process_response("hola")
    assert not complete
    assert session.current_step.value == "welcome"
    assert "responde *si*" in next_payload["response"].lower()

    complete, next_payload = session.process_response("Si")
    assert not complete
    assert "tu nombre" in next_payload["response"].lower()

    assert is_in_onboarding(phone)
    complete_onboarding_session(phone)


def test_onboarding_flow_collects_business_and_first_product_data():
    phone = "+5491112345678"
    session = create_onboarding_session(phone)

    complete, next_payload = session.process_response("Si")
    assert not complete
    assert "tu nombre" in next_payload["response"].lower()

    complete, next_payload = session.process_response("Sofia")
    assert not complete
    assert "nombre de tu negocio" in next_payload["response"].lower()

    complete, next_payload = session.process_response("Mi tienda")
    assert not complete
    assert "moneda" in next_payload["response"].lower()

    complete, next_payload = session.process_response("ARS")
    assert not complete
    assert "queda asi" in next_payload["response"].lower()

    complete, next_payload = session.process_response("Si")
    assert not complete
    assert "deseas agregar un producto a tu inventario" in next_payload["response"].lower()

    complete, next_payload = session.process_response("Pulsera coral")
    assert not complete
    assert "precio de venta" in next_payload["response"].lower()

    complete, next_payload = session.process_response("25000")
    assert complete
    assert "cargar stock" in next_payload["response"].lower()
    assert "ej: *agrega 10 unidades de pulsera coral*" in next_payload["response"].lower()
    assert "cuando cargues stock, tambien vas a poder" in next_payload["response"].lower()
    assert "ej: *vendi 2 pulsera coral*" in next_payload["response"].lower()
    assert "ej: *mostrame mi catalogo*" in next_payload["response"].lower()

    config = complete_onboarding_session(phone)
    assert not is_in_onboarding(phone)
    assert config is not None
    assert config["owner_name"] == "Sofia"
    assert config["business_name"] == "Mi tienda"
    assert config["language"] == "es"
    assert config["currency"] == "ARS"
    assert config["first_product_name"] == "Pulsera coral"
    assert config["first_product_cost_cents"] == 0
    assert config["first_product_price_cents"] == 2500000
    assert "first_goal" not in config
    assert "business_type" not in config
    assert "responde si para empezar" in config["prompts"]["welcome_message"].lower()


def test_onboarding_amount_parser_accepts_decimals_in_major_units():
    phone = "+5491112345000"
    session = create_onboarding_session(phone)

    complete, next_payload = session.process_response("Si")
    assert not complete
    complete, next_payload = session.process_response("Sofia")
    assert not complete
    complete, next_payload = session.process_response("Mi tienda")
    assert not complete
    complete, next_payload = session.process_response("ARS")
    assert not complete
    complete, next_payload = session.process_response("Si")
    assert not complete
    complete, next_payload = session.process_response("Pulsera coral")
    assert not complete
    assert "precio de venta" in next_payload["response"].lower()

    complete, next_payload = session.process_response("250.75")
    assert complete

    config = complete_onboarding_session(phone)
    assert config is not None
    assert config["first_product_cost_cents"] == 0
    assert config["first_product_price_cents"] == 25075


def test_onboarding_normalizes_conversational_product_name_answers():
    phone = "+5491112345001"
    session = create_onboarding_session(phone)

    complete, next_payload = session.process_response("Si")
    assert not complete
    complete, next_payload = session.process_response("Sofia")
    assert not complete
    complete, next_payload = session.process_response("Mi tienda")
    assert not complete
    complete, next_payload = session.process_response("ARS")
    assert not complete
    complete, next_payload = session.process_response("Si")
    assert not complete

    complete, next_payload = session.process_response("Vendo medias")
    assert not complete
    assert "precio de venta" in next_payload["response"].lower()

    complete_onboarding_session(phone)


def test_default_tenant_prompt_is_neutral():
    from tenant_manager import TenantManager

    manager = TenantManager()
    config = manager._get_default_config()

    assert "asistente virtual" in config["prompts"]["welcome_message"].lower()
    assert "negocio" in config["prompts"]["system_prompt"].lower()
