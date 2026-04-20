"""
Onboarding Agent - configuracion inicial interactiva de nuevos clientes.

Hace preguntas al usuario para crear su negocio personalizado.
"""
from enum import Enum
from typing import Any, Dict, Optional


class OnboardingStep(Enum):
    """Pasos del proceso de onboarding."""

    WELCOME = "welcome"
    OWNER_NAME = "owner_name"
    BUSINESS_NAME = "business_name"
    CURRENCY = "currency"
    CONFIRMATION = "confirmation"
    COMPLETE = "complete"


class OnboardingSession:
    """Sesion de onboarding para un cliente."""

    def __init__(self, phone_number: str):
        """
        Initialize onboarding session.

        Args:
            phone_number: Client's phone number
        """
        self.phone_number = phone_number
        self.current_step = OnboardingStep.WELCOME
        self.data: Dict[str, Any] = {}

    @staticmethod
    def _clean_text(user_message: str, default: str = "") -> str:
        text = " ".join(str(user_message or "").replace("\n", " ").replace("\r", " ").split())
        return text or default

    @staticmethod
    def _normalize_currency(user_message: str) -> str:
        text = OnboardingSession._clean_text(user_message).upper()
        if text in {"USD", "ARS", "EUR", "BRL"}:
            return text
        return "USD"

    def get_next_message(self) -> str:
        """
        Get the next message to send to the user based on current step.

        Returns:
            Message to send
        """
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
        if self.current_step == OnboardingStep.COMPLETE:
            return self._complete_message()

        return "Error en el proceso de configuracion."

    def process_response(self, user_message: str) -> tuple[bool, str]:
        """
        Process user response and advance to next step.

        Args:
            user_message: User's response

        Returns:
            Tuple of (is_complete, next_message)
        """
        if self.current_step == OnboardingStep.WELCOME:
            self.current_step = OnboardingStep.OWNER_NAME
            return False, self.get_next_message()

        if self.current_step == OnboardingStep.OWNER_NAME:
            self.data["owner_name"] = self._clean_text(user_message, "Tu nombre")
            self.current_step = OnboardingStep.BUSINESS_NAME
            return False, self.get_next_message()

        if self.current_step == OnboardingStep.BUSINESS_NAME:
            self.data["business_name"] = self._clean_text(user_message, "Mi negocio")
            self.current_step = OnboardingStep.CURRENCY
            return False, self.get_next_message()

        if self.current_step == OnboardingStep.CURRENCY:
            self.data["currency"] = self._normalize_currency(user_message)
            self.current_step = OnboardingStep.CONFIRMATION
            return False, self.get_next_message()

        if self.current_step == OnboardingStep.CONFIRMATION:
            response = self._clean_text(user_message).lower()
            if response in {"si", "yes", "s", "y", "confirmar", "ok", "dale", "listo"}:
                self.current_step = OnboardingStep.COMPLETE
                return True, self.get_next_message()

            # Restart
            self.current_step = OnboardingStep.WELCOME
            self.data = {}
            return False, "Ok, empecemos de nuevo.\n\n" + self.get_next_message()

        return False, "No entendi tu respuesta. Por favor intenta de nuevo."

    def _welcome_message(self) -> str:
        return """Hola, soy tu asistente virtual para ayudarte con tu negocio.

Te voy a hacer unas preguntas cortas para dejar todo listo.

Listo para empezar? Responde *Si* para continuar."""

    def _owner_name_message(self) -> str:
        return """Perfecto. Como te llamas?

Usare ese nombre para dirigirme a vos."""

    def _business_name_message(self) -> str:
        owner_name = self.data.get("owner_name", "").strip()
        prefix = f"Gracias, {owner_name}.\n\n" if owner_name else ""
        return f"""{prefix}Como se llama tu negocio?

Ejemplo: "Tienda de Maria", "Accesorios Luna", "Panaderia del Centro"."""

    def _currency_message(self) -> str:
        return """En que moneda trabajas?

Opciones: USD, ARS, EUR, BRL

Responde solo con el codigo."""

    def _confirmation_message(self) -> str:
        config_summary = f"""
Resumen de tu configuracion:

Negocio: {self.data.get('business_name')}
Tu nombre: {self.data.get('owner_name')}
Idioma: es
Moneda: {self.data.get('currency', 'USD')}

Todo correcto? Responde *Si* para confirmar o *No* para empezar de nuevo."""

        return config_summary

    def _complete_message(self) -> str:
        business_name = self.data.get("business_name", "Tu negocio")
        return f"""Listo!

Tu negocio {business_name} ya quedo configurado.

Ahora puedes:
- Consultar stock: "Cuanto stock tengo?"
- Registrar ventas: "Vendi 2 pulseras"
- Agregar productos: "Crear producto nuevo"
- Registrar gastos: "Gaste 50 en materiales"
- Ver ganancias: "Cuanto gane este mes?"

En que puedo ayudarte?"""

    def get_config(self) -> Dict[str, Any]:
        """Get the collected configuration data."""
        currency = self.data.get("currency", "USD")
        business_name = self.data.get("business_name", "Mi negocio")
        owner_name = self.data.get("owner_name", "")

        return {
            "business_name": business_name,
            "owner_name": owner_name,
            "currency": currency,
            "language": "es",
            "timezone": "America/Argentina/Buenos_Aires",
            "prompts": {
                "system_prompt": (
                    f"Eres el asistente virtual de {business_name}. "
                    "Ayudas con ventas, inventario, gastos y analisis de ganancias."
                ),
                "welcome_message": (
                    "Hola, soy tu asistente virtual para ayudarte con tu negocio. "
                    "En que puedo ayudarte?"
                ),
            },
            "features": {
                "audio_enabled": True,
                "sales_enabled": True,
                "expenses_enabled": True,
                "inventory_enabled": True,
            },
        }


# Active onboarding sessions
_active_sessions: Dict[str, OnboardingSession] = {}


def get_onboarding_session(phone_number: str) -> Optional[OnboardingSession]:
    """Get active onboarding session for a phone number."""
    return _active_sessions.get(phone_number)


def create_onboarding_session(phone_number: str) -> OnboardingSession:
    """Create a new onboarding session."""
    session = OnboardingSession(phone_number)
    _active_sessions[phone_number] = session
    return session


def complete_onboarding_session(phone_number: str) -> Optional[Dict[str, Any]]:
    """Complete and remove onboarding session, return collected config."""
    session = _active_sessions.pop(phone_number, None)
    if session:
        return session.get_config()
    return None


def is_in_onboarding(phone_number: str) -> bool:
    """Check if a phone number is in onboarding process."""
    return phone_number in _active_sessions
