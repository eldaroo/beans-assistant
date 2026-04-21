from onboarding_agent import (
    complete_onboarding_session,
    create_onboarding_session,
    is_in_onboarding,
)


def test_onboarding_starts_with_welcome_and_first_real_question():
    phone = "+5491112345678"
    session = create_onboarding_session(phone)
    intro_payload = session.get_intro_payload()

    assert is_in_onboarding(phone)
    assert "bienvenido" in intro_payload["response"].lower()
    assert "ventas, stock y gastos" in intro_payload["response"].lower()
    assert "cómo te gustaría que te llame" in intro_payload["response"].lower()

    complete, next_payload = session.process_response("Dario")
    assert not complete
    assert "cómo se llama tu negocio" in next_payload["response"].lower()

    assert is_in_onboarding(phone)
    complete_onboarding_session(phone)


def test_onboarding_flow_collects_business_and_first_product_data():
    phone = "+5491112345678"
    session = create_onboarding_session(phone)

    complete, next_payload = session.process_response("Sofia")
    assert not complete
    assert "cómo se llama tu negocio" in next_payload["response"].lower()

    complete, next_payload = session.process_response("Mi tienda")
    assert not complete
    assert "moneda" in next_payload["response"].lower()

    complete, next_payload = session.process_response("ARS")
    assert not complete
    assert "ya tengo lo básico de tu negocio" in next_payload["response"].lower()
    assert "cómo se llama" in next_payload["response"].lower()

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
    assert "ventas, stock y gastos" in config["prompts"]["welcome_message"].lower()


def test_onboarding_amount_parser_accepts_decimals_in_major_units():
    phone = "+5491112345000"
    session = create_onboarding_session(phone)

    complete, next_payload = session.process_response("Sofia")
    assert not complete
    complete, next_payload = session.process_response("Mi tienda")
    assert not complete
    complete, next_payload = session.process_response("ARS")
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

    complete, next_payload = session.process_response("Sofia")
    assert not complete
    complete, next_payload = session.process_response("Mi tienda")
    assert not complete
    complete, next_payload = session.process_response("ARS")
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
