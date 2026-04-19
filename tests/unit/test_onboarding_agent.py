from onboarding_agent import (
    OnboardingSession,
    complete_onboarding_session,
    create_onboarding_session,
    is_in_onboarding,
)


def test_onboarding_flow_is_neutral_and_collects_config():
    phone = "+5491112345678"
    session = create_onboarding_session(phone)

    assert is_in_onboarding(phone)
    assert "asistente virtual" in session.get_next_message().lower()

    complete, next_message = session.process_response("hola")
    assert not complete
    assert "como te llamas" in next_message.lower()

    complete, next_message = session.process_response("Sofia")
    assert not complete
    assert "como se llama tu negocio" in next_message.lower()

    complete, next_message = session.process_response("Mi tienda")
    assert not complete
    assert "idioma" in next_message.lower()

    complete, next_message = session.process_response("EN")
    assert not complete
    assert "moneda" in next_message.lower()

    complete, next_message = session.process_response("ARS")
    assert not complete
    assert "que queres hacer primero" in next_message.lower()

    complete, next_message = session.process_response("registrar una venta")
    assert not complete
    assert "resumen de tu configuracion" in next_message.lower()

    complete, next_message = session.process_response("Si")
    assert complete
    assert "ya quedo configurado" in next_message.lower()

    config = complete_onboarding_session(phone)
    assert not is_in_onboarding(phone)
    assert config is not None
    assert config["owner_name"] == "Sofia"
    assert config["business_name"] == "Mi tienda"
    assert config["language"] == "en"
    assert config["currency"] == "ARS"
    assert config["first_goal"] == "registrar una venta"
    assert config["business_type"] == "registrar una venta"
    assert "asistente virtual" in config["prompts"]["welcome_message"].lower()


def test_default_tenant_prompt_is_neutral():
    from tenant_manager import TenantManager

    manager = TenantManager()
    config = manager._get_default_config()

    assert "asistente virtual" in config["prompts"]["welcome_message"].lower()
    assert "negocio" in config["prompts"]["system_prompt"].lower()
