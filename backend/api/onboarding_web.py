"""Web onboarding API endpoint (M3.3 dispatcher).

Backend seam between the spectacle screen + chat shell and the
LLM-driven onboarding flow per ADR-002. The contract here is
intentionally additive: a request `{ message }` and a response
`{ response, metadata: { step, complete, captured?, tool_calls?, redirect_to?, error? } }`.

Gating: the FastAPI app mounts this router with
`Depends(require_pending_session)`, so the only callers are
authenticated pending sessions issued by the OAuth callback (M1).

The dispatcher:
    1. Loads (or creates) the pending session row from M3.1's repo.
    2. Renders the system prompt and replays history.
    3. Invokes Gemini with the bound tool list (M3.2).
    4. Dispatches any tool calls (recursion cap of 4 per turn,
       2 LLM calls max per turn per ADR-002).
    5. Persists the new state and history.
    6. Returns the assistant text plus the per-tool metadata cards.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request, Response
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from pydantic import BaseModel, Field, ValidationError

from backend.repositories.app_users_repository import AppUsersRepository
from backend.services.auth_service import SESSION_COOKIE_NAME, AuthService
from backend.repositories.pending_onboarding_repository import (
    PendingOnboardingRepository,
)
from backend.services.onboarding_llm_prompt import build_system_prompt
from backend.services.onboarding_llm_tools import (
    TOOL_REGISTRY,
    ToolOk,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# Per ADR-002 "Loop control": 30s wallclock per user turn; max 4 tool
# calls dispatched per turn (defensive recursion cap).
_LLM_TIMEOUT_SECONDS = 30.0
_MAX_TOOL_CALLS_PER_TURN = 4


class OnboardingWebMessage(BaseModel):
    """Incoming onboarding-web message from the spectacle / chat shell."""

    message: str


class OnboardingWebResponse(BaseModel):
    """Outgoing reply rendered as the assistant bubble."""

    response: str
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_STEP_ORDER: tuple[tuple[str, str], ...] = (
    ("business_name", "business_name"),
    ("phone", "phone"),
    ("currency", "currency"),
    ("language", "language"),
)


def _infer_step(state: dict) -> str:
    """Map the captured state to a single-word step label.

    Walks the canonical capture order and returns the first missing
    field; once name + phone + currency + language are all present,
    returns ``confirm`` (waiting on the user's go-ahead) or ``complete``
    if ``tenant_created`` is set.
    """
    if not isinstance(state, dict):
        return "greeting"
    if state.get("tenant_created"):
        return "complete"
    for field, label in _STEP_ORDER:
        if not state.get(field):
            return label
    return "confirm"


def _diff_state(before: dict, after: dict) -> dict:
    """Return only the keys whose values differ between before and after."""
    before = before or {}
    after = after or {}
    diff: dict[str, Any] = {}
    for k, v in after.items():
        if before.get(k) != v:
            diff[k] = v
    return diff


def _llm_for_tools_with_bindings():
    """Build a Gemini client with the M3.2 tool registry bound.

    Lazy: import the factory inside the call so the module stays
    importable when GOOGLE_API_KEY is absent (the M2 frontend can still
    load `/onboarding`; the dispatcher will return a `metadata.error =
    "llm_unavailable"` on first POST).
    """
    from llm import get_llm_for_tools

    llm = get_llm_for_tools()
    tool_models = [model for model, _executor in TOOL_REGISTRY.values()]
    return llm.bind_tools(tool_models)


def _history_to_messages(history: list[dict]) -> list:
    """Replay the persisted history into LangChain message objects."""
    out = []
    for entry in history or []:
        role = entry.get("role")
        content = entry.get("content", "") or ""
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
        # "tool" / "system" entries are not replayed; the system prompt
        # is rebuilt fresh each turn from current state.
    return out


def _ai_text(ai_response) -> str:
    """Pull the user-facing text out of a LangChain AIMessage."""
    if ai_response is None:
        return ""
    content = getattr(ai_response, "content", None)
    if isinstance(content, list):
        # Some Gemini responses come back as a list of parts.
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    if content is None:
        return ""
    return str(content)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/web", response_model=OnboardingWebResponse)
async def handle_onboarding_web(
    payload: OnboardingWebMessage,
    request: Request,
    response: Response,
) -> OnboardingWebResponse:
    """Run a single Gemini-driven onboarding turn.

    Replaces the M2 keyword stub. Request/response shape is preserved;
    `metadata` grows with the new fields specified in ADR-002.
    """
    pending = getattr(request.state, "pending", None) or {}
    email = pending.get("email", "")
    google_name = pending.get("name", "") or ""

    if not email:
        # The M1 dependency already guarantees an email; this is a
        # belt-and-suspenders guard so a misconfigured test fixture
        # surfaces clearly instead of crashing on a missing key.
        return OnboardingWebResponse(
            response="La sesión venció. Iniciá sesión de nuevo.",
            metadata={"error": "session_expired", "complete": False},
        )

    repo = PendingOnboardingRepository()

    try:
        session_row = repo.get(email)
        if session_row is None:
            session_row = repo.upsert(
                email=email, state={}, history=[], turn_count=0
            )
    except Exception:
        logger.exception("pending_onboarding repo error")
        return OnboardingWebResponse(
            response="Algo se rompió. Probá en un minuto.",
            metadata={"error": "db_error", "complete": False},
        )

    state_before = dict(session_row.get("state") or {})
    history = list(session_row.get("history") or [])
    turn_count = int(session_row.get("turn_count") or 0)

    # Append the user message to history for replay + persistence.
    user_msg = {
        "role": "user",
        "content": payload.message or "",
        "ts": datetime.utcnow().isoformat(),
    }
    history.append(user_msg)

    # Build the messages for Gemini. Stateless from the LLM's perspective:
    # the state lives in the system prompt (rendered fresh each turn from
    # the DB row). Replaying the full history confuses Gemini-2.5-flash
    # when a previous turn asked a narrow question and the user replies
    # with broad info — it focuses on the narrow ask and skips tool calls.
    # Empirically, system + current user message produces the correct
    # multi-tool-call response. The persisted history stays for audit /
    # replay; we just don't feed it to the LLM.
    sys_prompt = build_system_prompt(state_before, google_name, email)
    messages: list = [SystemMessage(content=sys_prompt), HumanMessage(content=payload.message)]

    # Lazy LLM build (catches a missing API key as `llm_unavailable`).
    try:
        llm = _llm_for_tools_with_bindings()
    except Exception:
        logger.exception("Gemini client init failed")
        return OnboardingWebResponse(
            response="Se cortó la conexión. Probá de nuevo en un momento.",
            metadata={"error": "llm_unavailable", "complete": False},
        )

    # First LLM call.
    try:
        ai_response = await asyncio.wait_for(
            asyncio.to_thread(llm.invoke, messages),
            timeout=_LLM_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("Gemini timeout on onboarding turn")
        return OnboardingWebResponse(
            response="Se cortó la conexión. Probá de nuevo en un momento.",
            metadata={"error": "llm_unavailable", "complete": False},
        )
    except Exception:
        logger.exception("Gemini error on onboarding turn")
        return OnboardingWebResponse(
            response="Se cortó la conexión. Probá de nuevo en un momento.",
            metadata={"error": "llm_unavailable", "complete": False},
        )

    # Dispatch any tool calls.
    tool_call_metadata: list[dict] = []
    redirect_to: str | None = None

    raw_tool_calls = getattr(ai_response, "tool_calls", None) or []

    # Build a reverse lookup so the LLM can call tools by either:
    #   - the snake_case registry key (capture_phone, confirm_and_create_tenant)
    #   - the Pydantic class name as Gemini sometimes emits it (CapturePhoneArgs)
    # Without this normalization, Gemini's class-name calls are silently dropped.
    _name_to_key: dict[str, str] = {}
    for _key, (_model, _exec) in TOOL_REGISTRY.items():
        _name_to_key[_key] = _key
        _name_to_key[_model.__name__] = _key
    if raw_tool_calls:
        for tc in raw_tool_calls[:_MAX_TOOL_CALLS_PER_TURN]:
            tool_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            tool_args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", None)
            tool_call_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)

            tool_key = _name_to_key.get(tool_name) if tool_name else None
            if not tool_key:
                # ADR-002 failure-mode: silently skip unknown tools.
                continue

            arg_model, executor = TOOL_REGISTRY[tool_key]
            # Normalize the metadata to use the snake_case registry key so
            # the frontend's beans-tool-call-cards match expectations.
            tool_name = tool_key
            try:
                args_obj = arg_model(**(tool_args or {}))
            except ValidationError:
                tool_call_metadata.append(
                    {
                        "tool": tool_name,
                        "status": "failure",
                        "label_es": "Argumento invalido.",
                        "payload": {"ok": False, "error": "validation_error"},
                    }
                )
                continue

            try:
                result = executor(email, args_obj)
            except Exception:
                logger.exception("tool executor crashed")
                tool_call_metadata.append(
                    {
                        "tool": tool_name,
                        "status": "failure",
                        "label_es": "Algo se rompió. Probá en un minuto.",
                        "payload": {"ok": False, "error": "db_error"},
                    }
                )
                continue

            label = (
                getattr(result, "label_es", None)
                or getattr(result, "message_es", "")
                or ""
            )
            tool_call_metadata.append(
                {
                    "tool": tool_name,
                    "status": "success" if getattr(result, "ok", False) else "failure",
                    "label_es": label,
                    "payload": result.model_dump(),
                }
            )

            if isinstance(result, ToolOk):
                rt = result.captured.get("redirect_to")
                if isinstance(rt, str):
                    redirect_to = rt

            # Feed the tool result back to the LLM for the second call.
            try:
                tool_payload_json = json.dumps(result.model_dump(), default=str)
            except Exception:
                tool_payload_json = "{}"
            messages.append(
                ToolMessage(
                    content=tool_payload_json,
                    tool_call_id=tool_call_id or tool_name,
                )
            )

        # Second LLM call: produce the user-facing reply with tool
        # results in context. Best-effort; on failure we synthesize
        # a minimal acknowledgement so the user is not left hanging.
        try:
            ai_response = await asyncio.wait_for(
                asyncio.to_thread(llm.invoke, messages),
                timeout=_LLM_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, Exception):
            logger.exception("Gemini second-turn error; using fallback text")

            class _Stub:
                content = "Listo."
                tool_calls: list = []

            ai_response = _Stub()

    reply_text = _ai_text(ai_response) or "Listo."

    # Re-read state in case executors mutated it; persist the new
    # history + bumped turn count UNLESS the confirm path already
    # deleted the pending row (we must not resurrect it).
    try:
        refreshed = repo.get(email)
    except Exception:
        refreshed = None

    if refreshed is None:
        # Confirm path: pending row deleted in the same transaction as
        # the tenants insert. Don't re-create it. Carry forward the
        # state we know from the executor's captured payload.
        state_after = dict(state_before)
        if redirect_to is not None:
            state_after["tenant_created"] = True
    else:
        state_after = refreshed.get("state", state_before)
        history.append(
            {
                "role": "assistant",
                "content": reply_text,
                "ts": datetime.utcnow().isoformat(),
            }
        )
        try:
            repo.upsert(
                email=email,
                state=state_after,
                history=history,
                turn_count=turn_count + 1,
            )
        except Exception:
            logger.exception("pending_onboarding upsert failed; continuing")

    complete = redirect_to is not None or bool(state_after.get("tenant_created"))

    # M4 cookie swap: when the user just created their tenant, the pending
    # cookie no longer authorizes anything (the row was deleted in the
    # confirm transaction). Issue an active session cookie now so the
    # frontend's redirect to /tenants/{phone} authenticates cleanly.
    if complete and redirect_to:
        phone_from_state = state_after.get("phone") or ""
        if phone_from_state:
            try:
                auth = AuthService()
                # Re-fetch the just-created app_user so we have its real id.
                app_user = AppUsersRepository().get_by_email(email)
                if app_user:
                    active_token = auth.issue_session(app_user)
                    response.set_cookie(
                        key=SESSION_COOKIE_NAME,
                        value=active_token,
                        max_age=auth.ttl_seconds,
                        httponly=True,
                        secure=os.getenv("COOKIE_SECURE", "true").lower() == "true",
                        samesite="lax",
                        domain=os.getenv("COOKIE_DOMAIN") or None,
                        path="/",
                    )
            except Exception:
                logger.exception("active session swap failed; user will need to /login")

    metadata: dict[str, Any] = {
        "step": _infer_step(state_after),
        "complete": complete,
        "captured": _diff_state(state_before, state_after),
        "tool_calls": tool_call_metadata,
        "redirect_to": redirect_to,
    }

    return OnboardingWebResponse(response=reply_text, metadata=metadata)
