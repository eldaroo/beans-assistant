"""Salvaged helpers kept after the old multi-agent Timonel was retired (spec 007 M5).

The LangGraph brain (graph.py and the router / decomposer / expander / resolver / safe_node /
state / read_agent / write_agent nodes) was removed when the native tool-use agent became the
only chat path. What remains here are the pure, reusable helpers the rest of the app still
uses: the named Spanish error copy, SKU composition, attribute keywords, and the shared
missing-field renderer. None of them import a model or the retired graph.
"""

from .error_copy import compose_error_response, supported_classes

__all__ = [
    "compose_error_response",
    "supported_classes",
]
