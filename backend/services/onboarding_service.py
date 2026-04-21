"""Service layer for WhatsApp onboarding flow."""

import re
import unicodedata

from backend.api.tenant_scope import tenant_scope
from backend.models.schemas import TenantCreate
from backend.models.schemas import ProductCreate
from backend.services.products_service import ProductConflictError, ProductsService
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

    def __init__(
        self,
        tenants_service: TenantsService | None = None,
        products_service: ProductsService | None = None,
    ):
        self.tenants_service = tenants_service or TenantsService()
        self.products_service = products_service or ProductsService()

    def _resolve_phone(self, phone: str) -> str:
        return self.tenants_service.repository.tenant_manager.normalize_phone_number(phone)

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        ascii_value = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_value).strip("-").upper()
        return slug or "PRODUCTO"

    def _create_first_product(self, phone: str, config: dict) -> bool:
        product_name = config.get("first_product_name")
        unit_cost_cents = config.get("first_product_cost_cents", 0)
        unit_price_cents = config.get("first_product_price_cents")

        if not product_name or unit_cost_cents is None or unit_price_cents is None:
            return False

        base_sku = self._slugify(product_name)
        for attempt in range(1, 6):
            sku = base_sku if attempt == 1 else f"{base_sku}-{attempt}"
            payload = ProductCreate(
                sku=sku,
                name=product_name,
                description=None,
                unit_cost_cents=unit_cost_cents,
                unit_price_cents=unit_price_cents,
            )
            try:
                with tenant_scope(phone):
                    self.products_service.create_product(phone=phone, payload=payload)
                return True
            except ProductConflictError:
                continue

        raise ProductConflictError(f"Could not generate a unique SKU for onboarding product '{product_name}'")

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
                "messages": None,
                "metadata": {
                    "onboarding_complete": True,
                    "tenant_created": False,
                    "tenant_exists": True,
                    "product_created": False,
                    "phone_number": normalized_phone,
                },
            }

        session = get_onboarding_session(normalized_phone)
        if session is None:
            session = create_onboarding_session(normalized_phone)
            payload = session.get_intro_payload()
            return {
                "response": payload["response"],
                "messages": payload.get("messages"),
                "metadata": {
                    "onboarding_complete": False,
                    "tenant_created": False,
                    "tenant_exists": False,
                    "product_created": False,
                    "phone_number": normalized_phone,
                    "step": session.current_step.value,
                    "phase": session.current_phase(),
                },
            }

        is_complete, next_payload = session.process_response(message)

        if not is_complete:
            return {
                "response": next_payload["response"],
                "messages": next_payload.get("messages"),
                "metadata": {
                    "onboarding_complete": False,
                    "tenant_created": False,
                    "tenant_exists": False,
                    "product_created": False,
                    "phone_number": normalized_phone,
                    "step": session.current_step.value,
                    "phase": session.current_phase(),
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
        product_created = False
        try:
            self.tenants_service.create_tenant(payload, extra_config=config)
            tenant_created = True
            product_created = self._create_first_product(normalized_phone, config)
        except TenantConflictError:
            tenant_created = False

        return {
            "response": next_payload["response"],
            "messages": next_payload.get("messages"),
            "metadata": {
                "onboarding_complete": True,
                "tenant_created": tenant_created,
                "product_created": product_created,
                "tenant_exists": True,
                "phone_number": normalized_phone,
                "step": OnboardingStep.COMPLETE.value,
                "phase": "ready",
            },
        }

    def is_active(self, phone: str) -> bool:
        normalized_phone = self._resolve_phone(phone)
        return is_in_onboarding(normalized_phone)
