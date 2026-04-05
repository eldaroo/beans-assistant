"""Service layer for chat simulation and tenant chat use-cases."""

import os
import time
from collections import defaultdict, deque
from typing import Any

import database
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

        context_text = "\n".join(history_lines)
        return (
            "Contexto de conversación reciente:\n"
            f"{context_text}\n\n"
            f"Mensaje actual: {message}"
        )

    @classmethod
    def _append_history(cls, phone: str, user_message: str, bot_response: str):
        history_key = cls._history_key(phone)
        cls._expire_if_stale(history_key)
        history = cls._history_by_key[history_key]
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": bot_response or ""})

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
    def _invoke_graph(cls, phone: str, message: str) -> dict:
        graph = cls._get_graph()
        message_with_context = cls._build_message_with_context(phone, message)
        initial_state = {
            "messages": [],
            "user_input": message_with_context,
            "phone": phone,
            "sender": phone,
            "normalized_entities": {},
            "metadata": {},
        }
        return graph.invoke(initial_state)

    @classmethod
    def simulate_chat(cls, phone: str, message: str) -> tuple[str, dict]:
        result = cls._invoke_graph(phone=phone, message=message)

        bot_response = ""
        if "messages" in result and len(result["messages"]) > 0:
            bot_response = cls._extract_message_content(result["messages"][-1])

        cls._append_history(phone=phone, user_message=message, bot_response=bot_response)
        return bot_response, result.get("metadata", {})

    @classmethod
    def chat_with_tenant(cls, phone: str, message: str) -> tuple[str, dict]:
        tenant_manager = TenantManager()
        normalized_phone = tenant_manager.normalize_phone_number(phone)
        if not tenant_manager.tenant_exists(normalized_phone):
            raise ChatTenantNotFoundError(f"Tenant {normalized_phone} not found")

        db_path = tenant_manager.get_tenant_db_path(normalized_phone)
        token = database.set_tenant_db_path(db_path)
        try:
            result = cls._invoke_graph(phone=normalized_phone, message=message)

            bot_response = ""
            if result.get("final_answer"):
                bot_response = result["final_answer"]
            elif "messages" in result and len(result["messages"]) > 0:
                user_facing_messages = []
                for msg in result["messages"]:
                    content = cls._extract_message_content(msg)
                    if not content.startswith("[Router]") and not content.startswith("[Read]") and \
                       not content.startswith("[Write]") and not content.startswith("[Resolver]"):
                        user_facing_messages.append(content)

                if user_facing_messages:
                    bot_response = user_facing_messages[-1]
                else:
                    bot_response = cls._extract_message_content(result["messages"][-1])

            metadata = {
                "intent": result.get("intent"),
                "operation_type": result.get("operation_type"),
                "confidence": result.get("confidence"),
            }
            cls._append_history(phone=normalized_phone, user_message=message, bot_response=bot_response)
            return bot_response, metadata
        finally:
            database.reset_tenant_db_path(token)
