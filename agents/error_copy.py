"""
error_copy — named Spanish recovery copy for the five error classes the
graph emits via `safe_node`.

Voice rules: no em-dashes, no en-dashes, no exclamations, no emojis, no
hype words. Every line ends with a parenthetical incident id so the
operator can correlate the user's report with the structured log line.

Used by `backend/services/chat_service.py` (T-004 envelope) to render
the response field when `state["error"]` is present. The frontend
extends `ERROR_FALLBACK_COPY` with the same five keys; both surfaces
must stay in sync if the dictionary changes.
"""
from __future__ import annotations

from typing import Iterable, Optional


# Default placeholder for the {hint} slot in the missing_field copy when
# the agent did not name a specific field. Kept human and short.
_DEFAULT_MISSING_HINT = "el detalle que me faltó"


_ERROR_COPY: dict[str, str] = {
    "unknown_product": (
        "No reconocí el producto que mencionaste. Repetímelo si querés, "
        "o decime el nombre exacto. (incidente {incident_id})"
    ),
    "missing_field": (
        "Me falta un dato para procesar esto. ¿Podés decirme {hint}? "
        "(incidente {incident_id})"
    ),
    "network": (
        "Tuve un problema técnico procesando tu mensaje. Probá de nuevo "
        "en un momento. (incidente {incident_id})"
    ),
    "llm_unavailable": (
        "El asistente no pudo responder ahora. Probá de nuevo en un "
        "momento. (incidente {incident_id})"
    ),
    # Kaze recovery line. Holds the thread open instead of dead-ending.
    "ambiguous_input": (
        "Eso no me salió. Volvamos a lo de los productos. "
        "(incidente {incident_id})"
    ),
}


def supported_classes() -> Iterable[str]:
    """The exact set of error_class values this module renders."""
    return tuple(_ERROR_COPY.keys())


def compose_error_response(
    error_class: str,
    incident_id: str,
    *,
    hint: Optional[str] = None,
) -> str:
    """Render the Spanish recovery line for `error_class`.

    Args:
        error_class: One of the five supported classes. Anything else
            falls back to `llm_unavailable` so the user always gets
            something readable rather than a Python KeyError leaking out.
        incident_id: Short correlation id from `safe_node`. Substituted
            into the trailing parenthetical.
        hint: Used only for `missing_field`. When omitted, a Spanish
            default ("el detalle que me faltó") is substituted.

    Returns:
        The rendered Spanish line, ready to ship to the user.
    """
    template = _ERROR_COPY.get(error_class) or _ERROR_COPY["llm_unavailable"]
    rendered = template.format(
        incident_id=incident_id,
        hint=(hint or _DEFAULT_MISSING_HINT),
    )
    return rendered


__all__ = ["compose_error_response", "supported_classes"]
