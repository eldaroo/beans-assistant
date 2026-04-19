"""Service layer for WhatsApp onboarding flow."""

from backend.models.schemas import TenantCreate
from backend.services.tenants_service import TenantConflictError, TenantsService
from onboarding_agent import (
    OnboardingStep,
    complete_onboarding_session,
    create_onboarding_session,
    get_onboarding_session,
    is_in_onboarding,
)


class OnboardingService:
    """Drive the interactive onboarding conversation and tenant creation."""

    def __init__(self, tenants_service: TenantsService | None = None):
        self.tenants_service = tenants_service or TenantsService()

    def _resolve_phone(self, phone: str) -> str:
        return self.tenants_service.repository.tenant_manager.normalize_phone_number(phone)

    def handle_message(self, phone: str, message: str, sender_name: str | None = None) -> dict:
        normalized_phone = self._resolve_phone(phone)
        tenant_manager = self.tenants_service.repository.tenant_manager

        if tenant_manager.tenant_exists(normalized_phone):
            config = tenant_manager.get_tenant_config(normalized_phone) or {}
            business_name = config.get("business_name", "Tu negocio")
            return {
                "response": (
                    f"Tu negocio *{business_name}* ya esta configurado. "
                    "Escribime al chat normal para seguir."
                ),
                "metadata": {
                    "onboarding_complete": True,
                    "tenant_created": False,
                    "tenant_exists": True,
                    "phone_number": normalized_phone,
                },
            }

        session = get_onboarding_session(normalized_phone)
        if session is None:
            session = create_onboarding_session(normalized_phone)

        is_complete, next_message = session.process_response(message)

        if not is_complete:
            return {
                "response": next_message,
                "metadata": {
                    "onboarding_complete": False,
                    "tenant_created": False,
                    "tenant_exists": False,
                    "phone_number": normalized_phone,
                    "step": session.current_step.value,
                },
            }

        config = complete_onboarding_session(normalized_phone) or {}
        payload = TenantCreate(
            phone_number=normalized_phone,
            business_name=config.get("business_name", "Mi negocio"),
            owner_name=config.get("owner_name") or sender_name,
            currency=config.get("currency", "USD"),
            language=config.get("language", "es"),
        )

        tenant_created = False
        try:
            self.tenants_service.create_tenant(payload, extra_config=config)
            tenant_created = True
        except TenantConflictError:
            tenant_created = False

        return {
            "response": next_message,
            "metadata": {
                "onboarding_complete": True,
                "tenant_created": tenant_created,
                "tenant_exists": True,
                "phone_number": normalized_phone,
                "step": OnboardingStep.COMPLETE.value,
            },
        }

    def is_active(self, phone: str) -> bool:
        normalized_phone = self._resolve_phone(phone)
        return is_in_onboarding(normalized_phone)
