"""
Onboarding Agent - configuracion inicial interactiva de nuevos clientes.

Hace preguntas al usuario para crear su negocio personalizado.
"""
from enum import Enum
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import unicodedata
from typing import Any, Dict, Optional


WELCOME_ASSET_KEY = "onboarding_welcome"
AFFIRMATIVE_RESPONSES = {"si", "sí", "yes", "s", "y", "confirmar", "ok", "dale", "listo", "empezar"}
NEGATIVE_RESPONSES = {"no", "n", "reiniciar", "de nuevo"}
VALID_CURRENCIES = {"USD", "ARS", "EUR", "BRL"}


class OnboardingStep(Enum):
    """Pasos del proceso de onboarding."""

    WELCOME = "welcome"
    OWNER_NAME = "owner_name"
    BUSINESS_NAME = "business_name"
    CURRENCY = "currency"
    CONFIRMATION = "confirmation"
    FIRST_PRODUCT_NAME = "first_product_name"
    FIRST_PRODUCT_COST = "first_product_cost"
    FIRST_PRODUCT_PRICE = "first_product_price"
    COMPLETE = "complete"


class OnboardingSession:
    """Sesion de onboarding para un cliente."""

    def __init__(self, phone_number: str):
        self.phone_number = phone_number
        self.current_step = OnboardingStep.WELCOME
        self.data: Dict[str, Any] = {}

    @staticmethod
    def _clean_text(user_message: str, default: str = "") -> str:
        text = " ".join(str(user_message or "").replace("\n", " ").replace("\r", " ").split())
        return text or default

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower().strip()

    def _is_affirmative(self, user_message: str) -> bool:
        return self._normalize_text(self._clean_text(user_message)) in AFFIRMATIVE_RESPONSES

    def _is_negative(self, user_message: str) -> bool:
        return self._normalize_text(self._clean_text(user_message)) in NEGATIVE_RESPONSES

    @staticmethod
    def _normalize_currency(user_message: str) -> Optional[str]:
        text = OnboardingSession._clean_text(user_message).upper()
        if text in VALID_CURRENCIES:
            return text
        return None

    @staticmethod
    def _parse_amount_cents(user_message: str) -> Optional[int]:
        text = OnboardingSession._clean_text(user_message)
        if not text:
            return None

        normalized = re.sub(r"[^\d,.\-]", "", text)
        if not normalized or normalized.startswith("-"):
            return None

        separators = [char for char in normalized if char in ",."]
        if not separators:
            amount = Decimal(normalized)
        else:
            last_separator_index = max(normalized.rfind(","), normalized.rfind("."))
            integer_part = re.sub(r"[,.]", "", normalized[:last_separator_index])
            decimal_part = normalized[last_separator_index + 1 :]

            if not integer_part and not decimal_part:
                return None

            if decimal_part and len(decimal_part) <= 2:
                normalized_number = f"{integer_part or '0'}.{decimal_part}"
            elif decimal_part and len(decimal_part) == 3:
                normalized_number = f"{(integer_part or '0')}{decimal_part}"
            else:
                normalized_number = re.sub(r"[,.]", "", normalized)

            try:
                amount = Decimal(normalized_number)
            except InvalidOperation:
                return None

        try:
            cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except InvalidOperation:
            return None

        return cents if cents > 0 else None

    def current_phase(self) -> str:
        if self.current_step in {
            OnboardingStep.WELCOME,
            OnboardingStep.OWNER_NAME,
            OnboardingStep.BUSINESS_NAME,
            OnboardingStep.CURRENCY,
            OnboardingStep.CONFIRMATION,
        }:
            return "setup"
        if self.current_step in {
            OnboardingStep.FIRST_PRODUCT_NAME,
            OnboardingStep.FIRST_PRODUCT_COST,
            OnboardingStep.FIRST_PRODUCT_PRICE,
        }:
            return "catalog"
        return "ready"

    def get_response_payload(self) -> dict:
        message = self.get_next_message()
        payload = {"response": message, "messages": None}

        if self.current_step == OnboardingStep.WELCOME:
            payload["messages"] = [
                {
                    "type": "image",
                    "asset_key": WELCOME_ASSET_KEY,
                    "caption": "Beans assistant",
                },
                {
                    "type": "text",
                    "text": message,
                },
            ]

        return payload

    def get_next_message(self) -> str:
        if self.current_step == OnboardingStep.WELCOME:
            return self._welcome_message()
        if self.current_step == OnboardingStep.OWNER_NAME:
            return self._owner_name_message()
        if self.current_step == OnboardingStep.BUSINESS_NAME:
            return self._business_name_message()
        if self.current_step == OnboardingStep.CURRENCY:
            return self._currency_message()
        if self.current_step == OnboardingStep.CONFIRMATION:
            return self._confirmation_message()
        if self.current_step == OnboardingStep.FIRST_PRODUCT_NAME:
            return self._first_product_name_message()
        if self.current_step == OnboardingStep.FIRST_PRODUCT_COST:
            return self._first_product_cost_message()
        if self.current_step == OnboardingStep.FIRST_PRODUCT_PRICE:
            return self._first_product_price_message()
        if self.current_step == OnboardingStep.COMPLETE:
            return self._complete_message()

        return "Error en el proceso de configuracion."

    def process_response(self, user_message: str) -> tuple[bool, dict]:
        if self.current_step == OnboardingStep.WELCOME:
            if self._is_affirmative(user_message):
                self.current_step = OnboardingStep.OWNER_NAME
                return False, self.get_response_payload()

            return False, {
                "response": (
                    "Necesito que me confirmes para arrancar.\n\n"
                    "Responde *Si* y seguimos con el paso 1 de 2."
                ),
                "messages": None,
            }

        if self.current_step == OnboardingStep.OWNER_NAME:
            owner_name = self._clean_text(user_message)
            if not owner_name:
                return False, {
                    "response": "Todavia no me dijiste tu nombre. Escribilo y seguimos.",
                    "messages": None,
                }

            self.data["owner_name"] = owner_name
            self.current_step = OnboardingStep.BUSINESS_NAME
            return False, self.get_response_payload()

        if self.current_step == OnboardingStep.BUSINESS_NAME:
            business_name = self._clean_text(user_message)
            if not business_name:
                return False, {
                    "response": "Necesito el nombre de tu negocio para seguir.",
                    "messages": None,
                }

            self.data["business_name"] = business_name
            self.current_step = OnboardingStep.CURRENCY
            return False, self.get_response_payload()

        if self.current_step == OnboardingStep.CURRENCY:
            currency = self._normalize_currency(user_message)
            if not currency:
                return False, {
                    "response": "Pasamela como uno de estos codigos: *USD, ARS, EUR o BRL*.",
                    "messages": None,
                }

            self.data["currency"] = currency
            self.current_step = OnboardingStep.CONFIRMATION
            return False, self.get_response_payload()

        if self.current_step == OnboardingStep.CONFIRMATION:
            if self._is_affirmative(user_message):
                self.current_step = OnboardingStep.FIRST_PRODUCT_NAME
                return False, self.get_response_payload()

            if self._is_negative(user_message):
                self.current_step = OnboardingStep.WELCOME
                self.data = {}
                return False, {
                    "response": "Dale, reiniciemos desde cero cuando quieras.",
                    "messages": None,
                }

            return False, {
                "response": "Responde *Si* para seguir o *No* para arrancar de nuevo.",
                "messages": None,
            }

        if self.current_step == OnboardingStep.FIRST_PRODUCT_NAME:
            product_name = self._clean_text(user_message)
            if not product_name:
                return False, {
                    "response": "Decime el nombre del primer producto para dejar tu catalogo listo.",
                    "messages": None,
                }

            self.data["first_product_name"] = product_name
            self.current_step = OnboardingStep.FIRST_PRODUCT_COST
            return False, self.get_response_payload()

        if self.current_step == OnboardingStep.FIRST_PRODUCT_COST:
            amount = self._parse_amount_cents(user_message)
            if amount is None:
                return False, {
                    "response": "Pasame el costo solo como numero. Ejemplo: *12500*.",
                    "messages": None,
                }

            self.data["first_product_cost_cents"] = amount
            self.current_step = OnboardingStep.FIRST_PRODUCT_PRICE
            return False, self.get_response_payload()

        if self.current_step == OnboardingStep.FIRST_PRODUCT_PRICE:
            amount = self._parse_amount_cents(user_message)
            if amount is None:
                return False, {
                    "response": "Pasame el precio solo como numero. Ejemplo: *25000*.",
                    "messages": None,
                }

            self.data["first_product_price_cents"] = amount
            self.current_step = OnboardingStep.COMPLETE
            return True, self.get_response_payload()

        return False, {"response": "No entendi tu respuesta. Intenta de nuevo.", "messages": None}

    def _welcome_message(self) -> str:
        return (
            "Bienvenido a *Beans assistant*.\n\n"
            "Paso *1 de 2*: dejamos tu negocio configurado.\n"
            "Paso *2 de 2*: cargamos tu primer producto para que arranques con el catalogo listo.\n\n"
            "Si te va, arranquemos ahora.\n"
            "Responde *Si* para continuar."
        )

    def _owner_name_message(self) -> str:
        return (
            "Buenisimo, vamos con el paso *1 de 2*.\n\n"
            "Como te llamas?\n"
            "Voy a usar ese nombre para hablarte en el chat."
        )

    def _business_name_message(self) -> str:
        owner_name = self.data.get("owner_name", "").strip()
        prefix = f"Genial, {owner_name}.\n\n" if owner_name else ""
        return (
            f"{prefix}Como se llama tu negocio?\n\n"
            "Ejemplo: *Tienda de Maria*, *Accesorios Luna* o *Panaderia del Centro*."
        )

    def _currency_message(self) -> str:
        return (
            "Perfecto.\n\n"
            "En que moneda trabajas?\n"
            "Opciones: *USD, ARS, EUR, BRL*.\n\n"
            "Responde solo con el codigo."
        )

    def _confirmation_message(self) -> str:
        return (
            "Asi queda tu negocio:\n\n"
            f"Negocio: *{self.data.get('business_name')}*\n"
            f"Tu nombre: *{self.data.get('owner_name')}*\n"
            f"Moneda: *{self.data.get('currency', 'USD')}*\n\n"
            "Si esta bien, responde *Si* y seguimos con el primer producto."
        )

    def _first_product_name_message(self) -> str:
        return (
            "Listo, paso *1 de 2* completado.\n\n"
            "Ahora vamos con el paso *2 de 2*: tu primer producto.\n"
            "Como se llama?"
        )

    def _first_product_cost_message(self) -> str:
        product_name = self.data.get("first_product_name", "ese producto")
        return (
            f"Anotado: *{product_name}*.\n\n"
            "Ahora pasame el *costo* en tu moneda, solo como numero.\n"
            "Ejemplos: *12500* o *125,50*."
        )

    def _first_product_price_message(self) -> str:
        return (
            "Perfecto.\n\n"
            "Ahora pasame el *precio de venta* en tu moneda, solo como numero.\n"
            "Ejemplos: *25000* o *250,75*."
        )

    def _complete_message(self) -> str:
        business_name = self.data.get("business_name", "Tu negocio")
        product_name = self.data.get("first_product_name", "tu primer producto")
        return (
            f"Ya tenes *{business_name}* configurado.\n\n"
            f"Tu primer producto, *{product_name}*, quedo creado.\n"
            "Tu catalogo ya arranco.\n\n"
            "Proximo paso recomendado: *cargar stock* para empezar a moverlo.\n\n"
            "Desde ahora ya podes:\n"
            "- crear mas productos\n"
            "- cargar stock\n"
            "- registrar gastos\n"
            "- consultar tu catalogo\n\n"
            "Cuando cargues stock, despues tambien vas a poder registrar ventas y consultar stock actual."
        )

    def get_config(self) -> Dict[str, Any]:
        currency = self.data.get("currency", "USD")
        business_name = self.data.get("business_name", "Mi negocio")
        owner_name = self.data.get("owner_name", "")

        return {
            "business_name": business_name,
            "owner_name": owner_name,
            "currency": currency,
            "language": "es",
            "timezone": "America/Argentina/Buenos_Aires",
            "first_product_name": self.data.get("first_product_name"),
            "first_product_cost_cents": self.data.get("first_product_cost_cents"),
            "first_product_price_cents": self.data.get("first_product_price_cents"),
            "prompts": {
                "system_prompt": (
                    f"Eres el asistente virtual de {business_name}. "
                    "Ayudas con ventas, inventario, gastos y analisis de ganancias."
                ),
                "welcome_message": (
                    "Bienvenido a Beans assistant. Arranquemos con tu negocio y tu primer producto."
                ),
            },
            "features": {
                "audio_enabled": True,
                "sales_enabled": True,
                "expenses_enabled": True,
                "inventory_enabled": True,
            },
        }


_active_sessions: Dict[str, OnboardingSession] = {}


def get_onboarding_session(phone_number: str) -> Optional[OnboardingSession]:
    return _active_sessions.get(phone_number)


def create_onboarding_session(phone_number: str) -> OnboardingSession:
    session = OnboardingSession(phone_number)
    _active_sessions[phone_number] = session
    return session


def complete_onboarding_session(phone_number: str) -> Optional[Dict[str, Any]]:
    session = _active_sessions.pop(phone_number, None)
    if session:
        return session.get_config()
    return None


def is_in_onboarding(phone_number: str) -> bool:
    return phone_number in _active_sessions
