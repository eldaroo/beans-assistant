"""
Onboarding Agent - configuracion inicial interactiva de nuevos clientes.

Hace preguntas al usuario para crear su negocio personalizado.
"""
from enum import Enum
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import unicodedata
from typing import Any, Dict, Optional


AFFIRMATIVE_RESPONSES = {"si", "sí", "yes", "s", "y", "confirmar", "ok", "dale", "listo", "empezar"}
NEGATIVE_RESPONSES = {"no", "n", "reiniciar", "de nuevo"}
VALID_CURRENCIES = {"USD", "ARS", "EUR", "BRL"}


class OnboardingStep(Enum):
    """Pasos del proceso de onboarding."""

    OWNER_NAME = "owner_name"
    BUSINESS_NAME = "business_name"
    CURRENCY = "currency"
    FIRST_PRODUCT_NAME = "first_product_name"
    FIRST_PRODUCT_PRICE = "first_product_price"
    COMPLETE = "complete"


class OnboardingSession:
    """Sesion de onboarding para un cliente."""

    def __init__(self, phone_number: str):
        self.phone_number = phone_number
        self.current_step = OnboardingStep.OWNER_NAME
        self.data: Dict[str, Any] = {}

    @staticmethod
    def _clean_text(user_message: str, default: str = "") -> str:
        text = " ".join(str(user_message or "").replace("\n", " ").replace("\r", " ").split())
        return text or default

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower().strip()

    @classmethod
    def _normalize_product_name_answer(cls, user_message: str) -> str:
        text = cls._clean_text(user_message)
        normalized = cls._normalize_text(text)

        conversational_prefixes = (
            "vendo ",
            "vendemos ",
            "trabajo con ",
            "trabajamos con ",
            "mi producto es ",
            "mi producto principal es ",
            "el producto es ",
            "vendo de todo, pero principalmente ",
        )

        for prefix in conversational_prefixes:
            if normalized.startswith(prefix):
                trimmed = text[len(prefix):].strip()
                return trimmed or text

        return text

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
            OnboardingStep.OWNER_NAME,
            OnboardingStep.BUSINESS_NAME,
            OnboardingStep.CURRENCY,
        }:
            return "setup"
        if self.current_step in {
            OnboardingStep.FIRST_PRODUCT_NAME,
            OnboardingStep.FIRST_PRODUCT_PRICE,
        }:
            return "catalog"
        return "ready"

    def get_intro_payload(self) -> dict:
        message = f"{self._welcome_message()}\n\n{self._owner_name_message()}"
        return {
            "response": message,
            "messages": [
                {
                    "type": "text",
                    "text": message,
                },
            ],
        }

    def get_response_payload(self) -> dict:
        message = self.get_next_message()
        return {"response": message, "messages": None}

    def get_next_message(self) -> str:
        if self.current_step == OnboardingStep.OWNER_NAME:
            return self._owner_name_message()
        if self.current_step == OnboardingStep.BUSINESS_NAME:
            return self._business_name_message()
        if self.current_step == OnboardingStep.CURRENCY:
            return self._currency_message()
        if self.current_step == OnboardingStep.FIRST_PRODUCT_NAME:
            return self._first_product_name_message()
        if self.current_step == OnboardingStep.FIRST_PRODUCT_PRICE:
            return self._first_product_price_message()
        if self.current_step == OnboardingStep.COMPLETE:
            return self._complete_message()

        return "Error en el proceso de configuracion."

    def process_response(self, user_message: str) -> tuple[bool, dict]:
        if self.current_step == OnboardingStep.OWNER_NAME:
            owner_name = self._clean_text(user_message)
            if not owner_name:
                return False, {
                    "response": "🙂 ¿Cómo te gustaría que te llame?",
                    "messages": None,
                }

            self.data["owner_name"] = owner_name
            self.current_step = OnboardingStep.BUSINESS_NAME
            return False, self.get_response_payload()

        if self.current_step == OnboardingStep.BUSINESS_NAME:
            business_name = self._clean_text(user_message)
            if not business_name:
                return False, {
                    "response": "✨ Decime el nombre de tu negocio y seguimos.",
                    "messages": None,
                }

            self.data["business_name"] = business_name
            self.current_step = OnboardingStep.CURRENCY
            return False, self.get_response_payload()

        if self.current_step == OnboardingStep.CURRENCY:
            currency = self._normalize_currency(user_message)
            if not currency:
                return False, {
                    "response": "💵 Decime tu moneda usando uno de estos códigos: *USD, ARS, EUR o BRL*.",
                    "messages": None,
                }

            self.data["currency"] = currency
            self.current_step = OnboardingStep.FIRST_PRODUCT_NAME
            return False, {
                "response": self._setup_complete_message(),
                "messages": None,
            }

        if self.current_step == OnboardingStep.FIRST_PRODUCT_NAME:
            product_name = self._normalize_product_name_answer(user_message)
            if not product_name:
                return False, {
                    "response": "📦 Decime el nombre de tu primer producto.",
                    "messages": None,
                }

            self.data["first_product_name"] = product_name
            self.current_step = OnboardingStep.FIRST_PRODUCT_PRICE
            return False, self.get_response_payload()

        if self.current_step == OnboardingStep.FIRST_PRODUCT_PRICE:
            amount = self._parse_amount_cents(user_message)
            if amount is None:
                return False, {
                    "response": "💸 Pasame el precio de venta solo como número. Ejemplo: *25000*.",
                    "messages": None,
                }

            self.data["first_product_price_cents"] = amount
            self.current_step = OnboardingStep.COMPLETE
            return True, self.get_response_payload()

        return False, {"response": "No entendi tu respuesta. Intenta de nuevo.", "messages": None}

    def _welcome_message(self) -> str:
        return (
            "👋 Bienvenido a *Beans assistant*.\n\n"
            "Te ayudo a llevar ventas, stock y gastos por WhatsApp."
        )

    def _owner_name_message(self) -> str:
        return "🙂 ¿Cómo te gustaría que te llame?"

    def _business_name_message(self) -> str:
        owner_name = self.data.get("owner_name", "").strip()
        prefix = f"Encantado, *{owner_name}*.\n\n" if owner_name else ""
        return f"{prefix}✨ ¿Cómo se llama tu negocio?"

    def _currency_message(self) -> str:
        return (
            "💵 ¿Con qué moneda trabajás?\n"
            "Podés responder: *USD, ARS, EUR o BRL*."
        )

    def _setup_complete_message(self) -> str:
        return (
            "🙌 Ya tengo lo básico de tu negocio:\n\n"
            f"Negocio: *{self.data.get('business_name')}*\n"
            f"Nombre: *{self.data.get('owner_name')}*\n"
            f"Moneda: *{self.data.get('currency', 'USD')}*\n\n"
            "Ahora vamos con tu primer producto.\n"
            "📦 ¿Cómo se llama?"
        )

    def _first_product_name_message(self) -> str:
        return "📦 ¿Cómo se llama tu primer producto?"

    def _first_product_price_message(self) -> str:
        product_name = self.data.get("first_product_name", "ese producto")
        return (
            f"✨ Perfecto, ya anoté *{product_name}*.\n\n"
            "¿Cuál es el *precio de venta*?\n"
            "Pasamelo solo como número."
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
            f"- crear mas productos. Ej: *Crea un producto buzo negro*\n"
            f"- cargar stock. Ej: *Agrega 10 unidades de {product_name}*\n"
            "- registrar gastos. Ej: *Registra un gasto de 5000 en envios*\n"
            "- consultar tu catalogo. Ej: *Mostrame mi catalogo*\n\n"
            "Cuando cargues stock, tambien vas a poder:\n"
            f"- registrar ventas. Ej: *Vendi 2 {product_name}*\n"
            f"- consultar stock actual. Ej: *Cuanto stock tengo de {product_name}?*"
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
            "first_product_cost_cents": self.data.get("first_product_cost_cents", 0),
            "first_product_price_cents": self.data.get("first_product_price_cents"),
            "prompts": {
                "system_prompt": (
                    f"Eres el asistente virtual de {business_name}. "
                    "Ayudas con ventas, inventario, gastos y analisis de ganancias."
                ),
                "welcome_message": (
                    "Bienvenido a Beans assistant. Te ayudo a llevar ventas, stock y gastos por WhatsApp."
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
