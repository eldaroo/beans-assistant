"""Service layer for chat simulation and tenant chat use-cases."""

import os
import time
from collections import defaultdict, deque
from typing import Any, Optional

from agents.error_copy import compose_error_response, supported_classes
from database_config import tenant_context
from graph import create_business_agent_graph
from tenant_manager import TenantManager


class ChatTenantNotFoundError(ValueError):
    """Raised when tenant chat is requested for an unknown tenant."""


class ChatService:
    """Encapsulates chat graph invocation and response extraction."""

    _graph = None
    _context_max_turns = int(os.getenv("CHAT_CONTEXT_MAX_TURNS", "6"))
    _context_ttl_seconds = int(os.getenv("CHAT_CONTEXT_TTL_SECONDS", "1800"))
    _history_by_key: dict[str, deque[dict[str, str]]] = defaultdict(
        lambda: deque(maxlen=ChatService._context_max_turns * 2)
    )
    _last_seen_by_key: dict[str, float] = {}

    @classmethod
    def _get_graph(cls):
        if cls._graph is None:
            cls._graph = create_business_agent_graph()
        return cls._graph

    @staticmethod
    def _history_key(phone: str) -> str:
        return f"phone:{phone}"

    @classmethod
    def _expire_if_stale(cls, history_key: str):
        now = time.time()
        last_seen = cls._last_seen_by_key.get(history_key)
        if last_seen and (now - last_seen) > cls._context_ttl_seconds:
            cls._history_by_key.pop(history_key, None)
            cls._last_seen_by_key.pop(history_key, None)
        cls._last_seen_by_key[history_key] = now

    @classmethod
    def _build_message_with_context(cls, phone: str, message: str) -> str:
        history_key = cls._history_key(phone)
        cls._expire_if_stale(history_key)
        history = cls._history_by_key.get(history_key)
        if not history:
            return message

        history_lines = []
        for entry in history:
            role = "Usuario" if entry.get("role") == "user" else "Asistente"
            content = entry.get("content", "").strip()
            if content:
                history_lines.append(f"{role}: {content}")

        if not history_lines:
            return message

        # If the previous assistant turn left the conversation in an AMBIGUOUS
        # disambiguation state (the bot asked which of two intents the user
        # meant), prepend a marker the router can read so the next turn
        # interprets the user's reply as the disambiguation answer instead of
        # re-classifying cold.
        last_assistant = next(
            (entry for entry in reversed(history) if entry.get("role") == "assistant"),
            None,
        )
        last_metadata = (last_assistant.get("metadata") if last_assistant else None) or {}
        ambiguity_marker = ""
        if last_metadata.get("last_intent") == "AMBIGUOUS":
            ambiguity_marker = (
                "[Nota: el turno anterior del asistente fue una pregunta de "
                "aclaracion entre dos intents. El usuario responde abajo.]\n"
            )

        # PR-A fix #3: when the previous turn left the conversation waiting
        # on missing fields (e.g. user said "vendo medias, pantaletas y
        # soquetes" and the bot replied asking for prices), the router on
        # the next turn re-classifies cold and loses the product names.
        # Inject a context marker that names the products and the pending
        # fields so the user's reply ("las medias 15, las pantaletas 20")
        # can be bound to the right entities downstream.
        pending_marker = ""
        pending_entities = last_metadata.get("pending_entities") or {}
        items = pending_entities.get("items") or []
        if items:
            names = [item.get("name") for item in items if item.get("name")]
            field_set: list[str] = []
            for item in items:
                for field in item.get("missing_fields") or []:
                    if field not in field_set:
                        field_set.append(field)
            field_translations = {
                "unit_price_cents": "el precio",
                "unit_price": "el precio",
                "unit_cost_cents": "el costo",
                "unit_cost": "el costo",
                "name": "el nombre",
                "quantity": "la cantidad",
                "amount_cents": "el monto",
                "description": "la descripcion",
            }
            friendly_fields = [field_translations.get(f, f) for f in field_set] or ["datos"]
            fields_str = ", ".join(friendly_fields)
            names_str = ", ".join(names) if names else "los productos previos"
            pending_marker = (
                f"[Contexto: turno anterior pidio {fields_str} para los productos: "
                f"{names_str}. El usuario ahora puede estar respondiendo con esos datos.]\n"
            )

        context_text = "\n".join(history_lines)
        return (
            "Contexto de conversación reciente:\n"
            f"{context_text}\n\n"
            f"{ambiguity_marker}"
            f"{pending_marker}"
            f"Mensaje actual: {message}"
        )

    @classmethod
    def _build_pending_entities(
        cls,
        operation_type: str | None,
        normalized_entities: dict | None,
        missing_fields: list[str] | None,
    ) -> dict | None:
        """Build the pending_entities metadata shape for the next turn.

        Designed to support N items (post-PR-B decomposer can populate
        multiple) but populates a single-item shape from the available
        normalized_entities when the resolver is on the legacy direct
        path. Returns None when there is nothing pending to track.
        """
        if not missing_fields:
            return None
        normalized_entities = normalized_entities or {}

        # Exclude marker fields. ambiguous_comma_name_split is consumed by
        # the final_answer node as a clarifier signal, not a real missing
        # data point we want to chase across turns.
        real_missing = [
            f for f in missing_fields if f != "ambiguous_comma_name_split"
        ]
        if not real_missing:
            return None

        items: list[dict] = []
        items_field = normalized_entities.get("items")
        if isinstance(items_field, list) and items_field:
            for raw in items_field:
                if not isinstance(raw, dict):
                    continue
                name = raw.get("name")
                if not name:
                    continue
                items.append({
                    "name": name,
                    "missing_fields": list(real_missing),
                })
        else:
            name = normalized_entities.get("name")
            if name:
                items.append({
                    "name": name,
                    "missing_fields": list(real_missing),
                })

        if not items:
            return None

        return {
            "operation_type": operation_type,
            "items": items,
        }

    @classmethod
    def _append_history(
        cls,
        phone: str,
        user_message: str,
        bot_response: str,
        bot_metadata: dict | None = None,
    ):
        history_key = cls._history_key(phone)
        cls._expire_if_stale(history_key)
        history = cls._history_by_key[history_key]
        history.append({"role": "user", "content": user_message})
        assistant_entry: dict[str, Any] = {
            "role": "assistant",
            "content": bot_response or "",
        }
        if bot_metadata:
            # Only persist the lean shape the router actually reads back.
            persisted = {
                key: bot_metadata.get(key)
                for key in ("last_intent", "operation_type")
                if bot_metadata.get(key) is not None
            }
            # PR-A fix #3: cross-turn missing-fields context. Persist
            # pending_entities only when the previous turn left fields
            # unresolved. Cleared automatically on the next assistant turn
            # because the caller only passes pending_entities when the
            # current turn still has missing_fields.
            pending = bot_metadata.get("pending_entities")
            if pending:
                persisted["pending_entities"] = pending
            if persisted:
                assistant_entry["metadata"] = persisted
        history.append(assistant_entry)

    @staticmethod
    def _extract_message_content(message_obj: Any) -> str:
        if hasattr(message_obj, "content"):
            return message_obj.content
        if isinstance(message_obj, dict) and "content" in message_obj:
            return message_obj["content"]
        if isinstance(message_obj, str):
            return message_obj
        return str(message_obj)

    @classmethod
    def _invoke_graph(cls, phone: str, message: str, owner_name: str | None = None) -> dict:
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"_invoke_graph: START with phone={phone}, message={message[:50]}...")
        try:
            graph = cls._get_graph()
            logger.info(f"_invoke_graph: got graph")
            
            message_with_context = cls._build_message_with_context(phone, message)
            logger.info(f"_invoke_graph: built message with context, length={len(message_with_context)}")
            
            initial_state = {
                "messages": [],
                "user_input": message_with_context,
                "phone": phone,
                "sender": phone,
                "normalized_entities": {},
                "metadata": {"owner_name": owner_name} if owner_name else {},
            }
            logger.info(f"_invoke_graph: initial_state keys={list(initial_state.keys())}")
            
            logger.info(f"_invoke_graph: calling graph.invoke()...")
            result = graph.invoke(initial_state)
            logger.info(f"_invoke_graph: graph.invoke() returned, result keys={list(result.keys())}")
            return result
        except Exception as e:
            logger.error(f"_invoke_graph: ERROR - {type(e).__name__}: {e}", exc_info=True)
            raise

    @classmethod
    def _build_envelope(cls, result: dict, fallback_response: str) -> dict:
        """Wrap a graph result in the public chat envelope (T-004).

        Shape:
            {
                "response": str,
                "metadata": {
                    "error_code": Optional[str],   # one of supported_classes() or None
                    "incident_id": Optional[str],  # short uuid prefix or None
                    "navigation": Optional[dict],  # {"tab": "..."} when emitted by an agent
                    # plus any other metadata the graph already carried
                    # (intent, operation_type, confidence, owner_name, etc).
                },
            }

        When `state["error"]` is set by safe_node, `error_code` and
        `incident_id` are populated and `response` is replaced with the
        named Spanish copy from `compose_error_response`. Otherwise they
        are None.
        """
        err = result.get("error")
        graph_metadata = dict(result.get("metadata") or {})

        # navigation is set by agents (write_agent on successful tool calls)
        # and surfaces unchanged. We do NOT keyword-scan the response text.
        navigation = graph_metadata.pop("navigation", None)

        if isinstance(err, dict) and err.get("class") in set(supported_classes()):
            error_code = err.get("class")
            incident_id = err.get("incident_id") or ""
            response = compose_error_response(error_code, incident_id)
            metadata = {
                **graph_metadata,
                "error_code": error_code,
                "incident_id": incident_id,
                "navigation": navigation,
            }
            return {"response": response, "metadata": metadata}

        metadata = {
            **graph_metadata,
            "error_code": None,
            "incident_id": None,
            "navigation": navigation,
        }
        return {"response": fallback_response, "metadata": metadata}

    @classmethod
    def simulate_chat(cls, phone: str, message: str) -> dict:
        result = cls._invoke_graph(phone=phone, message=message)

        bot_response = ""
        if "messages" in result and len(result["messages"]) > 0:
            bot_response = cls._extract_message_content(result["messages"][-1])

        envelope = cls._build_envelope(result, bot_response)
        cls._append_history(
            phone=phone,
            user_message=message,
            bot_response=envelope["response"],
        )
        return envelope

    @classmethod
    def chat_with_tenant(
        cls,
        phone: str,
        message: str,
        sender_name: str | None = None,
    ) -> dict:
        import logging
        logger = logging.getLogger(__name__)
        
        tenant_manager = TenantManager()
        normalized_phone = tenant_manager.normalize_phone_number(phone)
        resolved_phone = tenant_manager.resolve_tenant_phone(normalized_phone)
        clean_sender_name = tenant_manager.sanitize_owner_name(sender_name)
        logger.info(
            f"chat_with_tenant: phone={phone}, normalized={normalized_phone}, resolved={resolved_phone}, sender_name={clean_sender_name}"
        )

        if not resolved_phone:
            raise ChatTenantNotFoundError(f"Tenant {normalized_phone} not found")

        if clean_sender_name:
            tenant_manager.set_tenant_owner_name(resolved_phone, clean_sender_name)

        tenant_config = tenant_manager.get_tenant_config(resolved_phone) or {}
        owner_name = clean_sender_name or tenant_manager.sanitize_owner_name(
            tenant_config.get("owner_name")
        )
        if not owner_name:
            business_name = tenant_manager.sanitize_owner_name(tenant_config.get("business_name"))
            if business_name and not business_name.lower().startswith("tenant +"):
                owner_name = business_name

        logger.info(f"chat_with_tenant: setting tenant context for phone={resolved_phone}")
        with tenant_context(resolved_phone):
            logger.info(f"chat_with_tenant: invoking graph with message={message[:50]}...")
            result = cls._invoke_graph(phone=resolved_phone, message=message, owner_name=owner_name)
            logger.info(f"chat_with_tenant: graph returned result with keys={list(result.keys())}")

            bot_response = ""
            if result.get("final_answer"):
                bot_response = result["final_answer"]
                logger.info(f"chat_with_tenant: using final_answer={bot_response[:50]}...")
            elif "messages" in result and len(result["messages"]) > 0:
                logger.info(f"chat_with_tenant: processing {len(result['messages'])} messages")
                user_facing_messages = []
                for msg in result["messages"]:
                    content = cls._extract_message_content(msg)
                    if not content.startswith("[Router]") and not content.startswith("[Read]") and \
                       not content.startswith("[Write]") and not content.startswith("[Resolver]"):
                        user_facing_messages.append(content)

                if user_facing_messages:
                    bot_response = user_facing_messages[-1]
                    logger.info(f"chat_with_tenant: using user_facing message={bot_response[:50]}...")
                else:
                    bot_response = cls._extract_message_content(result["messages"][-1])
                    logger.info(f"chat_with_tenant: using last message={bot_response[:50]}...")
            else:
                logger.warning(f"chat_with_tenant: no final_answer or messages found in result")

            # Carry the agent-emitted navigation (if any) onto the
            # envelope. Set by write_agent on successful tool calls
            # only, never on disambiguation. See T-007.
            graph_metadata = result.get("metadata") or {}
            envelope_metadata: dict[str, Any] = {
                "intent": result.get("intent"),
                "operation_type": result.get("operation_type"),
                "confidence": result.get("confidence"),
                "navigation": graph_metadata.get("navigation"),
            }

            # Build the public envelope. When the graph wrote an error
            # delta (safe_node), `_build_envelope` swaps the response
            # for the named Spanish copy and populates error_code +
            # incident_id. When clean, response is the assistant
            # final_answer and error fields are None.
            envelope_input = {
                "error": result.get("error"),
                "metadata": envelope_metadata,
            }
            envelope = cls._build_envelope(envelope_input, bot_response)

            # PR-A fix #3: capture pending_entities when the current turn
            # finished with missing_fields, so the next turn can resolve
            # the user's reply against the named products.
            pending_entities = cls._build_pending_entities(
                operation_type=result.get("operation_type"),
                normalized_entities=result.get("normalized_entities"),
                missing_fields=result.get("missing_fields"),
            )
            logger.info(f"chat_with_tenant: appending to history for phone={resolved_phone}")
            cls._append_history(
                phone=resolved_phone,
                user_message=message,
                bot_response=envelope["response"],
                bot_metadata={
                    "last_intent": result.get("intent"),
                    "operation_type": result.get("operation_type"),
                    "pending_entities": pending_entities,
                },
            )
            logger.info(
                f"chat_with_tenant: returning response={envelope['response'][:50]}..."
            )
            return envelope
