import logging
import os
from typing import Optional

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

logger = logging.getLogger(__name__)

# ── Backend selection (spec 005) ────────────────────────────────────────────
#
# Timonel's brain (Router, Resolver fallback, Read, Decomposer) can run on Gemini OR on the
# Claude-subscription gateway (deploy/, Nomad job beans-ai). TIMONEL_LLM_BACKEND flips it:
#   TIMONEL_LLM_BACKEND=gateway   -> the warm Claude gateway (no API key)
#   TIMONEL_LLM_BACKEND=gemini    -> Gemini (the default, and the per-call fallback)
# Cutover is reversible and per-tenant: TIMONEL_LLM_BACKEND_<TENANT> overrides the global flag
# for one tenant, so a tenant can be moved onto Claude and rolled back without touching others.
#
# get_llm_for_tools() (the onboarding dispatcher) is out of this spec's scope: it uses Gemini
# function-calling (.bind_tools) rather than the JsonOutputParser path, so it stays Gemini-backed
# regardless of the flag.

BACKEND_GATEWAY = "gateway"
BACKEND_GEMINI = "gemini"


def _tenant_env_key(tenant_id: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in str(tenant_id)).upper()
    return "TIMONEL_LLM_BACKEND_" + safe


def resolve_backend(tenant_id: Optional[str] = None) -> str:
    """Return the active backend for a tenant: per-tenant override, else global, else gemini.

    An unrecognized value (a typo like 'gatway') resolves to itself and is handled downstream as
    Gemini (fail-closed), but we log it once so a cutover misconfiguration is visible instead of
    silently serving Gemini."""
    if tenant_id:
        override = os.getenv(_tenant_env_key(tenant_id))
        if override:
            b = override.strip().lower()
            if b not in (BACKEND_GATEWAY, BACKEND_GEMINI):
                logger.warning("TIMONEL_LLM_BACKEND for tenant %s is %r, not gateway|gemini; serving Gemini", tenant_id, b)
            return b
    b = (os.getenv("TIMONEL_LLM_BACKEND") or BACKEND_GEMINI).strip().lower()
    if b not in (BACKEND_GATEWAY, BACKEND_GEMINI):
        logger.warning("TIMONEL_LLM_BACKEND is %r, not gateway|gemini; serving Gemini", b)
    return b


# ── Gemini builders (unchanged behavior) ────────────────────────────────────

def _gemini_main() -> ChatGoogleGenerativeAI:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY (or OPENAI_API_KEY) is not set")

    requested_model = os.getenv("OPENAI_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
    supported_models = {"gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash-exp"}
    model = requested_model if requested_model in supported_models else "gemini-2.5-flash"

    print(f"DEBUG: Requested model: {requested_model}")
    print(f"DEBUG: Using model: {model}")

    temperature = float(os.getenv("OPENAI_TEMPERATURE") or os.getenv("GEMINI_TEMPERATURE") or "0.2")
    return ChatGoogleGenerativeAI(model=model, temperature=temperature, google_api_key=api_key)


def _gemini_tools() -> ChatGoogleGenerativeAI:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY (or OPENAI_API_KEY) is not set")

    requested_model = os.getenv("OPENAI_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
    supported_models = {"gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash-exp"}
    model = requested_model if requested_model in supported_models else "gemini-2.5-flash"

    temperature = float(os.getenv("OPENAI_TEMPERATURE") or os.getenv("GEMINI_TEMPERATURE") or "0.2")
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        google_api_key=api_key,
        convert_system_message_to_human=False,
    )


def _gemini_cheap() -> ChatGoogleGenerativeAI:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY (or OPENAI_API_KEY) is not set")

    model = os.getenv("GEMINI_CHEAP_MODEL", "gemini-2.5-flash")
    return ChatGoogleGenerativeAI(model=model, temperature=0.1, google_api_key=api_key)


# ── Per-call fallback (spec 005) ────────────────────────────────────────────
#
# On the gateway path, Timonel must never hard-fail on a model error/timeout. We wrap the
# ChatGateway with LangChain's with_fallbacks: on a GatewayError the chain falls back to Gemini
# (during cutover, when a key is present) and finally to a safe deterministic response (an empty
# JSON object the agents read defensively -> clarify). Set TIMONEL_LLM_FALLBACK=off to disable.


def _fallback_disabled() -> bool:
    return (os.getenv("TIMONEL_LLM_FALLBACK") or "on").strip().lower() in ("off", "0", "false", "no")


def _with_fallbacks(primary, gemini_builder):
    """Compose primary.with_fallbacks([Gemini?, SafeDefault]). gemini_builder is injected so a
    test can supply a stand-in; in production it is _gemini_main / _gemini_cheap."""
    if _fallback_disabled():
        return primary
    from llm_gateway import SafeDefaultChatModel

    fallbacks = []
    if os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY"):
        try:
            fallbacks.append(gemini_builder())
        except Exception:
            pass
    fallbacks.append(SafeDefaultChatModel())
    return primary.with_fallbacks(fallbacks)


# ── Public factories (backend-dispatching) ──────────────────────────────────

def get_llm(tenant_id: Optional[str] = None, backend: Optional[str] = None) -> BaseChatModel:
    """Main model for the router + read agent. Gemini by default; the Claude gateway (with a
    Gemini + safe-default fallback chain) when the backend selects it. Pass `backend` to pin the
    choice (the graph cache keys on a resolved backend so per-tenant cutover actually takes
    effect); otherwise it resolves from `tenant_id` then the global flag."""
    b = backend or resolve_backend(tenant_id)
    if b == BACKEND_GATEWAY:
        from llm_gateway import make_gateway_llm

        temperature = float(os.getenv("OPENAI_TEMPERATURE") or os.getenv("GEMINI_TEMPERATURE") or "0.2")
        return _with_fallbacks(make_gateway_llm(temperature=temperature), _gemini_main)
    return _gemini_main()


def get_llm_cheap(tenant_id: Optional[str] = None, backend: Optional[str] = None) -> BaseChatModel:
    """Fast model for disambiguation (resolver fallback + decomposer). Gemini by default; the
    Claude gateway (with fallback chain) when the backend selects it. `backend` pins the choice."""
    b = backend or resolve_backend(tenant_id)
    if b == BACKEND_GATEWAY:
        from llm_gateway import make_gateway_llm

        return _with_fallbacks(make_gateway_llm(temperature=0.1), _gemini_cheap)
    return _gemini_cheap()


def get_llm_for_tools() -> ChatGoogleGenerativeAI:
    """Tool-calling model for the M3.3 onboarding dispatcher. Out of spec 005 scope (it relies
    on Gemini .bind_tools function-calling, not the JsonOutputParser path), so it stays
    Gemini-backed regardless of TIMONEL_LLM_BACKEND."""
    return _gemini_tools()
