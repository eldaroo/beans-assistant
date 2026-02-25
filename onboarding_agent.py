"""
Onboarding Agent - Configuración inicial interactiva de nuevos clientes.

Hace preguntas al usuario para crear su negocio personalizado.
"""
from typing import Dict, Any, Optional
from enum import Enum


class OnboardingStep(Enum):
    """Pasos del proceso de onboarding."""
    WELCOME = "welcome"
    BUSINESS_NAME = "business_name"
    BUSINESS_TYPE = "business_type"
    CURRENCY = "currency"
    FIRST_PRODUCTS = "first_products"
    CONFIRMATION = "confirmation"
    COMPLETE = "complete"


class OnboardingSession:
    """Sesión de onboarding para un cliente."""

    def __init__(self, phone_number: str):
        """
        Initialize onboarding session.

        Args:
            phone_number: Client's phone number
        """
        self.phone_number = phone_number
        self.current_step = OnboardingStep.WELCOME
        self.data: Dict[str, Any] = {}

    def get_next_message(self) -> str:
        """
        Get the next message to send to the user based on current step.

        Returns:
            Message to send
        """
        if self.current_step == OnboardingStep.WELCOME:
            return self._welcome_message()
        elif self.current_step == OnboardingStep.BUSINESS_NAME:
            return self._business_name_message()
        elif self.current_step == OnboardingStep.BUSINESS_TYPE:
            return self._business_type_message()
        elif self.current_step == OnboardingStep.CURRENCY:
            return self._currency_message()
        elif self.current_step == OnboardingStep.FIRST_PRODUCTS:
            return self._first_products_message()
        elif self.current_step == OnboardingStep.CONFIRMATION:
            return self._confirmation_message()
        elif self.current_step == OnboardingStep.COMPLETE:
            return self._complete_message()

        return "Error en el proceso de configuración."

    def process_response(self, user_message: str) -> tuple[bool, str]:
        """
        Process user response and advance to next step.

        Args:
            user_message: User's response

        Returns:
            Tuple of (is_complete, next_message)
        """
        if self.current_step == OnboardingStep.WELCOME:
            # Just advance
            self.current_step = OnboardingStep.BUSINESS_NAME
            return False, self.get_next_message()

        elif self.current_step == OnboardingStep.BUSINESS_NAME:
            self.data["business_name"] = user_message.strip()
            self.current_step = OnboardingStep.BUSINESS_TYPE
            return False, self.get_next_message()

        elif self.current_step == OnboardingStep.BUSINESS_TYPE:
            self.data["business_type"] = user_message.strip()
            self.current_step = OnboardingStep.CURRENCY
            return False, self.get_next_message()

        elif self.current_step == OnboardingStep.CURRENCY:
            currency = user_message.strip().upper()
            if currency in ["USD", "ARS", "EUR", "BRL"]:
                self.data["currency"] = currency
            else:
                self.data["currency"] = "USD"  # Default

            self.current_step = OnboardingStep.FIRST_PRODUCTS
            return False, self.get_next_message()

        elif self.current_step == OnboardingStep.FIRST_PRODUCTS:
            response = user_message.strip().lower()
            if response in ["si", "sí", "yes", "s", "y"]:
                self.data["add_products_now"] = True
                self.current_step = OnboardingStep.CONFIRMATION
                return False, "Perfecto! Ahora podrás agregar productos cuando quieras.\n\n" + self.get_next_message()
            else:
                self.data["add_products_now"] = False
                self.current_step = OnboardingStep.CONFIRMATION
                return False, self.get_next_message()

        elif self.current_step == OnboardingStep.CONFIRMATION:
            response = user_message.strip().lower()
            if response in ["si", "sí", "yes", "s", "y", "confirmar", "ok"]:
                self.current_step = OnboardingStep.COMPLETE
                return True, self.get_next_message()
            else:
                # Restart
                self.current_step = OnboardingStep.WELCOME
                self.data = {}
                return False, "Ok, empecemos de nuevo.\n\n" + self.get_next_message()

        return False, "No entendí tu respuesta. Por favor intenta de nuevo."

    def _welcome_message(self) -> str:
        return """¡Bienvenido! 👋

Soy tu asistente de negocios inteligente. Veo que es la primera vez que me escribes.

Voy a hacerte algunas preguntas rápidas para configurar tu negocio. Te tomará solo 2 minutos.

¿Listo para empezar? Responde *Sí* para continuar."""

    def _business_name_message(self) -> str:
        return """Perfecto! Comencemos.

¿Cómo se llama tu negocio?

Ejemplo: "Beans&Co", "Tienda de María", "Accesorios Luna"..."""

    def _business_type_message(self) -> str:
        return f"""Genial, *{self.data.get('business_name')}*!

¿Qué tipo de negocio tienes?

Ejemplo: "Vendo pulseras artesanales", "Tienda de ropa", "Panadería"..."""

    def _currency_message(self) -> str:
        return """¿En qué moneda trabajas?

Opciones: USD, ARS, EUR, BRL

Responde solo con el código (ej: "USD")"""

    def _first_products_message(self) -> str:
        return """Perfecto!

¿Quieres que te ayude a cargar algunos productos ahora?

Responde *Sí* o *No*"""

    def _confirmation_message(self) -> str:
        config_summary = f"""
Resumen de tu configuración:

🏪 *Negocio:* {self.data.get('business_name')}
📋 *Tipo:* {self.data.get('business_type')}
💰 *Moneda:* {self.data.get('currency', 'USD')}

¿Todo correcto? Responde *Sí* para confirmar o *No* para empezar de nuevo."""

        return config_summary

    def _complete_message(self) -> str:
        return f"""¡Listo! ✅

Tu negocio *{self.data.get('business_name')}* está configurado.

Ahora puedes:
• Consultar stock: "¿Cuánto stock tengo?"
• Registrar ventas: "Vendí 2 pulseras doradas"
• Agregar productos: "Crear producto nuevo"
• Registrar gastos: "Gasté $50 en materiales"
• Ver ganancias: "¿Cuánto gané este mes?"

¿En qué puedo ayudarte?"""

    def get_config(self) -> Dict[str, Any]:
        """Get the collected configuration data."""
        return {
            "business_name": self.data.get("business_name", "Mi Negocio"),
            "business_type": self.data.get("business_type", ""),
            "currency": self.data.get("currency", "USD"),
            "language": "es",
            "timezone": "America/Argentina/Buenos_Aires",
            "prompts": {
                "system_prompt": f"Eres un asistente de negocios para {self.data.get('business_name')}. "
                                 f"Ayudas con ventas, inventario, gastos y análisis de ganancias.",
                "welcome_message": f"¡Hola! Soy el asistente de {self.data.get('business_name')}. ¿En qué puedo ayudarte?"
            },
            "features": {
                "audio_enabled": True,
                "sales_enabled": True,
                "expenses_enabled": True,
                "inventory_enabled": True
            }
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
