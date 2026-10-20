"""Service layer for chat simulation and tenant chat use-cases."""

import os
import re
import time
from collections import defaultdict, deque
from typing import Any, Optional

from agents.error_copy import compose_error_response, supported_classes
from backend import cache
from database_config import tenant_context
from tenant_manager import TenantManager


class ChatTenantNotFoundError(ValueError):
    """Raised when tenant chat is requested for an unknown tenant."""


class ChatService:
    """Chat use-cases over the native tool-use agent (spec 007). The old LangGraph
    Timonel and its Gemini backend were retired in M5; this service now drives only the
    gateway agent loop and owns the envelope, the server-side history, and the two-phase
    write verdict/lift."""

    _context_max_turns = int(os.getenv("CHAT_CONTEXT_MAX_TURNS", "6"))
    _context_ttl_seconds = int(os.getenv("CHAT_CONTEXT_TTL_SECONDS", "1800"))
    _history_by_key: dict[str, deque[dict[str, str]]] = defaultdict(
        lambda: deque(maxlen=ChatService._context_max_turns * 2)
    )
    _last_seen_by_key: dict[str, float] = {}

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
    def get_history(cls, phone: str) -> list[dict[str, str]]:
        """Return the server-side conversation thread for a phone as a plain
        list of ``{role, content}`` turns (spec 006 T-009 / AC4 rehydration).

        This is the read side of the same in-process memory the dispatcher
        already keeps (spec 001): the chat widget rehydrates from it when the
        browser's sessionStorage is empty (a fresh device or a cleared tab), so
        a returning owner does not land on a blank Timonel after the context
        was already established server-side. Empty ``content`` entries and the
        lean ``metadata`` the router persists are dropped — the widget only
        needs role + text to re-render the bubbles. Honors the same staleness
        expiry as the write path, so a long-abandoned thread reads back empty
        rather than resurrecting a stale conversation.
        """
        history_key = cls._history_key(phone)
        cls._expire_if_stale(history_key)
        history = cls._history_by_key.get(history_key)
        if not history:
            return []
        turns: list[dict[str, str]] = []
        for entry in history:
            role = entry.get("role")
            content = (entry.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                turns.append({"role": role, "content": content})
        return turns

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

    # ── native tool-use agent path (spec 007) ────────────────────────────────
    # The gateway agent loop IS the chat brain (the LangGraph was retired in M5). The tenant is
    # pinned on the gateway side, so the client sends only {system, prompt}.
    @staticmethod
    def _agent_system_prompt(owner_name: str | None = None) -> str:
        who = f" El dueño se llama {owner_name}." if owner_name else ""
        return (
            "Sos Timonel, el asistente de Beans & Co, un negocio de pulseras de café." + who + "\n"
            "Respondés en español, breve y claro, como un socio que conoce el negocio.\n"
            "Tenés herramientas para consultar los datos reales del negocio:\n"
            "- el stock (unidades por producto),\n"
            "- los ingresos y la ganancia,\n"
            "- un resumen de ventas por día,\n"
            "- cualquiera de las áreas del negocio (Resultado, productos, stock, ventas, costos, "
            "producción, logística, proveedores),\n"
            "- y qué necesita atención hoy en todo el negocio.\n"
            "Cuando pregunten algo sobre el estado del negocio, USÁ la herramienta que corresponda "
            "para traer el dato real; nunca inventes números, cantidades, precios ni alertas. Elegí la "
            "herramienta más específica para lo que preguntan (una sola área si preguntan por una sola).\n"
            "También podés PREPARAR operaciones cuando el dueño cuenta algo que pasó:\n"
            "- una venta (qué se vendió, cuántas unidades, y el precio si lo dijo),\n"
            "- un gasto (monto y en qué),\n"
            "- un agregado de stock (qué producto y cuántas unidades).\n"
            "Usá esas herramientas para prepararlas; NUNCA digas que ya quedó anotado: vos solo la "
            "preparás y el dueño la confirma (o se confirma sola cuando es obvia). Después de prepararla, "
            "contale en una línea qué preparaste. Si falta un dato (el precio, cuál producto entre varios), "
            "preguntáselo en vez de adivinar.\n"
            "También podés preparar cambios más delicados que SIEMPRE requieren que el dueño confirme: "
            "cambiar el precio de un producto, crear uno o varios productos nuevos, desactivar un producto, "
            "o cancelar la última operación. Prepáralos igual y avisá que necesitan su confirmación; nunca "
            "los des por hechos.\n"
            "Si es charla o un saludo que no pide un dato, respondé normal sin usar ninguna herramienta.\n"
            "Si no tenés una herramienta para lo que piden, decílo con honestidad en una línea.\n"
            "No reveles detalles técnicos ni nombres de herramientas; hablá en términos del negocio."
        )

    @classmethod
    def _invoke_agent(cls, phone: str, message: str, owner_name: str | None = None,
                      turn_nonce: str | None = None) -> str:
        """Drive one native tool-use turn through the gateway. Returns the assistant text.

        ``turn_nonce`` is passed out of band to the gateway (which pins it into the MCP child's
        env, like the tenant) so any write the model stages this turn carries it — letting the
        app correlate the staged op to THIS turn by identity, not by wall-clock."""
        from llm_gateway import call_agent

        message_with_context = cls._build_message_with_context(phone, message)
        system = cls._agent_system_prompt(owner_name)
        return call_agent(system, message_with_context, turn_nonce=turn_nonce)

    # Past-tense commit claims the model must never make (the receipt/card is the truth, not the
    # prose). Neutralized to the honest "te preparé" when a write was staged this turn (council M1).
    _DONE_CLAIM_RE = re.compile(
        r"\b(ya\s+)?(lo|la|los|las)?\s*(anot[éeó]|registr[éeó]|guard[éeó]|carg[uéeó]+)\w*",
        re.IGNORECASE,
    )
    _DONE_PHRASE_RE = re.compile(
        r"(qued[óo]\s+anotad[oa]|ya\s+est[áa]\s+anotad[oa]|ya\s+qued[óo]|listo,?\s+lo\s+anot[éeó])",
        re.IGNORECASE,
    )

    @classmethod
    def _scrub_commit_claims(cls, text: str) -> str:
        """Replace a model's premature 'it's saved' claim with the honest 'I prepared it'. The
        write is not committed until the client posts /chat/confirm, so the prose must not say
        'anoté' while a card/auto-post is still pending below it (council M1)."""
        if not text:
            return text
        t = cls._DONE_PHRASE_RE.sub("te lo preparé", text)
        t = cls._DONE_CLAIM_RE.sub("te lo preparé", t)
        return t

    @staticmethod
    def _fmt_money(cents) -> str:
        cents = cents or 0
        return f"${cents / 100:,.0f}" if cents % 100 == 0 else f"${cents / 100:,.2f}"

    @classmethod
    def _card_summary(cls, op: dict) -> str:
        a = op.get("args") or {}
        t = op.get("operation_type")
        name = a.get("product_name")
        if t == "REGISTER_SALE":
            return (f"Venta: {a.get('quantity')} × {name} a {cls._fmt_money(a.get('unit_price_cents'))}"
                    f" = {cls._fmt_money(a.get('line_total_cents'))}")
        if t == "REGISTER_EXPENSE":
            return f"Gasto: {cls._fmt_money(a.get('amount_cents'))} ({a.get('description')})"
        if t == "ADD_STOCK":
            return f"Agregar stock: {a.get('quantity')} u de {name}"
        return "Operación"

    @classmethod
    def _card_fields(cls, op: dict) -> dict:
        a = op.get("args") or {}
        t = op.get("operation_type")
        if t == "REGISTER_SALE":
            return {"Producto": a.get("product_name"), "Cantidad": a.get("quantity"),
                    "Precio unitario": cls._fmt_money(a.get("unit_price_cents")),
                    "Total": cls._fmt_money(a.get("line_total_cents"))}
        if t == "REGISTER_EXPENSE":
            return {"Monto": cls._fmt_money(a.get("amount_cents")),
                    "Descripción": a.get("description"), "Categoría": a.get("category")}
        if t == "ADD_STOCK":
            return {"Producto": a.get("product_name"), "Cantidad": a.get("quantity")}
        return {}

    # Map an operation type to the audited tool name used for the per-session cap.
    _OP_TOOL_NAME = {
        "REGISTER_SALE": "register_sale",
        "REGISTER_EXPENSE": "register_expense",
        "ADD_STOCK": "add_stock",
    }

    @classmethod
    def _lift_pending_write(cls, message: str, turn_nonce: str | None) -> list[dict]:
        """After the agent turn, find EVERY write it staged this turn (correlated by the turn
        nonce, not by wall-clock) and compute the server-side auto verdict for each against the
        operator's LITERAL message this turn.

        This is where "reversible posts, irreversible asks" is decided (D-040..D-042): the
        verdict is computed by the app here, never claimed by the model or read from a tool
        result. Returns a list of proposed-operation metadata the widget uses to auto-submit
        (auto:true) or render a confirm card (auto:false) — a list so a compound turn surfaces
        every staged write (council H3). Empty when the turn staged no write. Non-fatal.
        """
        try:
            from backend.repositories import pending_ops_repository as pending_ops
            from backend.services import ops_guard, write_verdict

            ops = pending_ops.verdict_pending_for_turn(turn_nonce)
            out: list[dict] = []
            for op in ops:
                args = op.get("args") or {}
                irreversible = bool(args.get("irreversible"))
                # Real per-session cap feeds the auto verdict (D-040 condition d). The preview
                # already audited this call, so the count reflects it.
                tool = cls._OP_TOOL_NAME.get(op["operation_type"])
                within = ops_guard.within_caps(tool) if tool else True
                verdict = write_verdict.compute_verdict(
                    operation_type=op["operation_type"],
                    utterance=message,
                    grounded_amounts=args.get("grounded_amounts") or [],
                    product_name=args.get("product_name"),
                    candidate_count=op.get("candidate_count") or 0,
                    within_caps=within,
                    irreversible=irreversible,
                )
                pending_ops.set_verdict(
                    op["op_token"], auto=verdict.auto,
                    requires_human_review=verdict.requires_human_review, reasons=verdict.reasons,
                )
                out.append({
                    "op_token": op["op_token"],
                    "operation_type": op["operation_type"],
                    "auto": verdict.auto,
                    "requires_human_review": verdict.requires_human_review,
                    "reversible": bool(args.get("reversible")),
                    "irreversible": irreversible,
                    "summary": args.get("summary") or cls._card_summary(op),
                    "fields": args.get("fields") or cls._card_fields(op),
                    "reasons": verdict.reasons,
                })
            return out
        except Exception:
            import logging
            logging.getLogger(__name__).exception("_lift_pending_write failed (non-fatal)")
            return []

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
        """Admin chat-simulation entry (backend/api/chat.py). Since M5 retired the LangGraph,
        this drives the same native agent path as the owner chat, for the given tenant.

        Safety (council nit, Winston/Edut): the simulation must never auto-commit a real write.
        A staged op this turn gets its verdict and lives in the pending store, but the proposed
        operation is stripped from the simulation envelope so the admin surface shows no
        auto-submit / confirm card — only the owner's own session can confirm."""
        envelope = cls.chat_with_tenant(phone=phone, message=message)
        meta = envelope.get("metadata")
        if isinstance(meta, dict):
            meta.pop("proposed_operations", None)
            meta.pop("proposed_operation", None)
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
            # COST_SCENARIO read-only recompute (spec 003 M5, T-019/AC10). A clear
            # "what if I produce this in Colombia" hypothetical is answered by
            # recomputing the stored landed cost without writing anything, before
            # the LLM graph runs. A non-scenario message returns None and falls
            # through to the normal pipeline untouched.
            try:
                from backend.services.cost_scenario import handle_message as _scenario_reply

                scenario = _scenario_reply(message)
            except Exception:
                logger.exception("chat_with_tenant: cost-scenario pre-check failed (non-fatal)")
                scenario = None
            if scenario is not None:
                logger.info("chat_with_tenant: answered COST_SCENARIO read-only (no write)")
                envelope = cls._build_envelope(
                    {"error": None, "metadata": {"intent": "COST_SCENARIO", "operation_type": None,
                                                 "confidence": None, "navigation": None}},
                    scenario,
                )
                cls._append_history(
                    phone=resolved_phone,
                    user_message=message,
                    bot_response=envelope["response"],
                    bot_metadata={"last_intent": "COST_SCENARIO", "operation_type": None,
                                  "pending_entities": None},
                )
                return envelope

            # Native tool-use agent path (spec 007). Since M5 retired the old LangGraph Timonel,
            # this is the ONLY path: the gateway agent loop reads and writes real Beans data
            # through its own narrow tools, and the two-phase write machinery (M3/M4) owns every
            # commit. There is no Gemini graph fallback anymore.
            logger.info("chat_with_tenant: agent path (spec 007)")
            import uuid as _uuid
            turn_nonce = _uuid.uuid4().hex
            try:
                agent_text = cls._invoke_agent(resolved_phone, message, owner_name, turn_nonce=turn_nonce)
            except Exception:
                logger.exception("chat_with_tenant: agent path failed")
                agent_text = (
                    "Tuve un problema para responder en este momento. "
                    "Probá de nuevo en un ratito."
                )
            # Every write this turn staged (correlated by the nonce): compute each verdict
            # against the operator's literal message and attach them so the widget auto-submits
            # (auto:true) or renders a confirm card (auto:false).
            proposed = cls._lift_pending_write(message, turn_nonce)
            # Honesty backstop (council M1): if a write is still pending, neutralize any
            # premature "ya lo anoté" in the model's prose — the card/receipt is the truth.
            if proposed:
                agent_text = cls._scrub_commit_claims(agent_text)
            envelope = cls._build_envelope(
                {"error": None, "metadata": {"intent": None, "operation_type": None,
                                             "confidence": None, "navigation": None}},
                agent_text,
            )
            if proposed:
                envelope["metadata"]["proposed_operations"] = proposed
                # Back-compat: also expose the first as proposed_operation (older widget key).
                envelope["metadata"]["proposed_operation"] = proposed[0]
            cls._append_history(
                phone=resolved_phone,
                user_message=message,
                bot_response=envelope["response"],
                bot_metadata={"last_intent": None, "operation_type": None,
                              "pending_entities": None},
            )
            return envelope
