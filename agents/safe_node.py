"""
safe_node — per-node fault containment for the Timonel LangGraph.

Wraps a graph node so that any exception it raises is caught, classified
into one of five short error_class strings, logged as a single line of
structured JSON, optionally tagged into Sentry, and surfaced into the
graph state as `state["error"]` instead of leaking up into the
dispatcher.

Contract:
    state["error"] = {
        "class": "<unknown_product|missing_field|network|llm_unavailable|ambiguous_input>",
        "node":  "<node name>",
        "msg":   "<exception str>",
        "incident_id": "<short uuid hex prefix>",
    }

The decorator never raises. A wrapped node always returns a dict the
LangGraph dispatcher can merge.

Used by `graph.py` to wrap every business node in `decomposer`,
`router`, `resolver`, `read_agent`, `write_agent`. Tests in
`tests/unit/test_safe_node.py`.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Callable, Dict


logger = logging.getLogger(__name__)


# Five error classes the chat envelope and copy module both speak.
ERROR_CLASSES = (
    "unknown_product",
    "missing_field",
    "network",
    "llm_unavailable",
    "ambiguous_input",
)


_UNKNOWN_PRODUCT_PAT = re.compile(
    r"\b("
    r"product[_ ]?not[_ ]?found"
    r"|unknown[_ ]?product"
    r"|no[_ ]?such[_ ]?product"
    r"|producto[_ ]?no[_ ]?(encontrado|existe)"
    r"|sku[_ ]?desconocido"
    r")\b",
    flags=re.IGNORECASE,
)


def _new_incident_id() -> str:
    """Short, copy-pasteable correlation id surfaced to the user."""
    return uuid.uuid4().hex[:10]


def _classify(exc: BaseException) -> str:
    """Map an exception to one of the five error_class values.

    Heuristic order matters: the most specific signal wins. Unknown
    falls back to llm_unavailable so the user sees the safer copy and
    the operator still gets the structured log line to debug from.
    """
    msg = str(exc) or exc.__class__.__name__

    # Network-shaped first: httpx / requests / generic socket errors.
    exc_type_name = exc.__class__.__name__
    exc_module = getattr(exc.__class__, "__module__", "") or ""
    if (
        exc_module.startswith("httpx")
        or exc_module.startswith("requests")
        or exc_module.startswith("urllib3")
        or exc_module.startswith("aiohttp")
        or exc_module == "socket"
        or "Timeout" in exc_type_name
        or "ConnectionError" in exc_type_name
        or "NetworkError" in exc_type_name
    ):
        return "network"

    # Unknown product: regex on the message text.
    if _UNKNOWN_PRODUCT_PAT.search(msg):
        return "unknown_product"

    # Missing field: KeyError / pydantic ValidationError / explicit phrasing.
    if isinstance(exc, KeyError):
        return "missing_field"
    if "ValidationError" in exc_type_name:
        return "missing_field"
    if re.search(r"\b(missing|required)\b.*\bfield\b", msg, flags=re.IGNORECASE):
        return "missing_field"

    # Ambiguous (rare from raw exceptions, but reserved for explicit raises).
    if re.search(r"\bambig", msg, flags=re.IGNORECASE):
        return "ambiguous_input"

    # Default safe bucket.
    return "llm_unavailable"


def _emit_structured_log(
    *,
    phone: str | None,
    intent: str | None,
    node: str,
    error_class: str,
    incident_id: str,
    msg: str,
) -> None:
    """One JSON line per exception. Operators grep this in the journal."""
    payload = {
        "event": "graph_node_exception",
        "phone": phone,
        "intent": intent,
        "node": node,
        "error_class": error_class,
        "incident_id": incident_id,
        "msg": msg,
    }
    logger.error(json.dumps(payload, ensure_ascii=False))


def _tag_sentry(
    *,
    node: str,
    error_class: str,
    incident_id: str,
    exc: BaseException,
) -> None:
    """Best-effort Sentry tagging. No-op if sentry_sdk is not installed."""
    try:
        import sentry_sdk  # type: ignore
    except Exception:  # noqa: BLE001
        return
    try:
        sentry_sdk.set_tag("error_class", error_class)
        sentry_sdk.set_tag("node", node)
        sentry_sdk.set_tag("incident_id", incident_id)
        sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        # Sentry failures must never bubble out of the safe wrapper.
        logger.debug("sentry_sdk tag/capture failed", exc_info=True)


def safe_node(node_name: str) -> Callable[[Callable[..., Dict[str, Any]]], Callable[..., Dict[str, Any]]]:
    """Decorator factory. `node_name` is the label written into state.error.node.

    Usage:
        @safe_node("router")
        def router(state):
            ...

    Or wrap an already-built callable:
        wrapped = safe_node("router")(router_fn)

    The decorator catches every exception, populates the typed error
    delta, emits a structured log line, optionally pings Sentry, and
    returns the delta so the graph keeps moving.
    """

    def decorator(fn: Callable[..., Dict[str, Any]]) -> Callable[..., Dict[str, Any]]:
        def wrapped(state: Dict[str, Any], *args: Any, **kwargs: Any) -> Dict[str, Any]:
            try:
                return fn(state, *args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                error_class = _classify(exc)
                incident_id = _new_incident_id()
                msg = str(exc) or exc.__class__.__name__
                phone = (state or {}).get("phone")
                intent = (state or {}).get("intent")

                _emit_structured_log(
                    phone=phone,
                    intent=intent,
                    node=node_name,
                    error_class=error_class,
                    incident_id=incident_id,
                    msg=msg,
                )
                _tag_sentry(
                    node=node_name,
                    error_class=error_class,
                    incident_id=incident_id,
                    exc=exc,
                )

                return {
                    "error": {
                        "class": error_class,
                        "node": node_name,
                        "msg": msg,
                        "incident_id": incident_id,
                    }
                }

        wrapped.__name__ = getattr(fn, "__name__", node_name)
        wrapped.__doc__ = fn.__doc__
        wrapped.__wrapped__ = fn  # type: ignore[attr-defined]
        return wrapped

    return decorator


__all__ = ["safe_node", "ERROR_CLASSES"]
