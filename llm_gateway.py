"""llm_gateway.py — Timonel's Claude-subscription backend client (spec 005).

This exposes the SAME interface Timonel's Gemini client exposes: a LangChain chat model that
the graph agents consume via ``PROMPT | llm | JsonOutputParser`` and ``.invoke(...)``. The only
difference is where the tokens come from — a warm Claude-subscription gateway (``deploy/``,
Nomad job ``beans-ai``) instead of the Gemini API. Every existing JsonOutputParser schema stays
untouched: ``ChatGateway`` returns text, the downstream parser coerces it to the same dicts.

No new dependency: the HTTP call is stdlib ``urllib``. Isolation is on the gateway side — this
client only sends ``{system, prompt}`` text and gets back text.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Optional

# First balanced JSON object in a reply (first { to last }). Mirrors gateway.mjs carveJson so a
# prose-wrapped reply ("Here is the JSON:\n{...}") parses through the unchanged JsonOutputParser
# exactly as clean JSON did. This is the output-shape-drift mitigation the council asked for: a
# tuned Gemini rarely wrapped its JSON, Claude sometimes does, and without carving those turns
# would skip the fallback (the parser sits outside with_fallbacks) and degrade to clarify.
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _carve_json_text(text: str) -> str:
    m = _JSON_OBJECT_RE.search(text or "")
    return m.group(0) if m else (text or "")

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

DEFAULT_GATEWAY_URL = "https://beans-ai.mdlautomations.duckdns.org"
DEFAULT_TIMEOUT = 30.0


class GatewayError(RuntimeError):
    """Raised when the gateway is unreachable, times out, or returns ``{ok: false}``.

    Carries a machine-readable ``code`` so callers (and the per-agent fallback in llm.py) can
    branch on the failure class rather than parse a string.
    """

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def gateway_url() -> str:
    return (os.getenv("BEANS_AI_GATEWAY_URL") or DEFAULT_GATEWAY_URL).rstrip("/")


def shared_secret() -> str:
    return os.getenv("BEANS_AI_SHARED_SECRET") or ""


def gateway_timeout() -> float:
    try:
        return float(os.getenv("BEANS_AI_GATEWAY_TIMEOUT") or DEFAULT_TIMEOUT)
    except ValueError:
        return DEFAULT_TIMEOUT


# Seam for tests: the single network call. Monkeypatch this to exercise the client offline.
def _http_post_json(url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # A 4xx/5xx still carries the gateway's named-error envelope in the body.
        return e.code, e.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        raise GatewayError("unreachable", str(getattr(e, "reason", e)))
    except TimeoutError as e:
        raise GatewayError("timeout", str(e) or "request timed out")


def call_gateway(
    system: str,
    prompt: str,
    *,
    json_schema: Optional[dict] = None,
    max_tokens: Optional[int] = None,
    url: Optional[str] = None,
    secret: Optional[str] = None,
    timeout: Optional[float] = None,
) -> dict:
    """POST one turn to the gateway's ``/run`` and return the parsed ``{ok, text|json, path}``.

    Raises ``GatewayError`` on transport failure or an ``{ok: false}`` envelope, so a caller can
    fall back to Gemini or a safe deterministic response (spec 005, per-call fallback).
    """
    base = (url or gateway_url()).rstrip("/")
    sec = secret if secret is not None else shared_secret()
    if not sec:
        raise GatewayError("no-secret", "BEANS_AI_SHARED_SECRET is not set")
    payload: dict[str, Any] = {"system": system or "", "prompt": prompt or ""}
    if json_schema is not None:
        payload["json_schema"] = json_schema
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    body = json.dumps(payload).encode("utf-8")
    headers = {"content-type": "application/json", "authorization": "Bearer " + sec}
    status, text = _http_post_json(base + "/run", headers, body, timeout or gateway_timeout())
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        raise GatewayError("bad-response", f"gateway returned non-JSON (status {status})")
    if not isinstance(data, dict) or not data.get("ok"):
        err = (data or {}).get("error") or {}
        raise GatewayError(
            str(err.get("code") or f"http-{status}"),
            str(err.get("message") or text[:200]),
        )
    return data


def call_agent(
    system: str,
    prompt: str,
    *,
    url: Optional[str] = None,
    secret: Optional[str] = None,
    timeout: Optional[float] = None,
    turn_nonce: Optional[str] = None,
) -> str:
    """POST one turn to the gateway's ``/run-agent`` (native tool-use) and return the assistant text.

    Unlike ``call_gateway`` (the tool-free classification path), this drives the agent loop: the
    gateway spawns a tool-enabled child that reads and (later) writes real Beans data through the
    beans MCP server. Returns the final text; raises ``GatewayError`` on transport failure or an
    ``{ok: false}`` envelope so the caller can surface an honest error. The tenant is pinned on the
    gateway side (out of band), so this sends only ``{system, prompt}``.
    """
    base = (url or gateway_url()).rstrip("/")
    sec = secret if secret is not None else shared_secret()
    if not sec:
        raise GatewayError("no-secret", "BEANS_AI_SHARED_SECRET is not set")
    payload = {"system": system or "", "prompt": prompt or ""}
    if turn_nonce:
        # Pinned out of band to the gateway, which injects it into the MCP child's env so any
        # staged write carries it (lets the app correlate the staged op to this turn by identity).
        payload["turn_nonce"] = turn_nonce
    body = json.dumps(payload).encode("utf-8")
    headers = {"content-type": "application/json", "authorization": "Bearer " + sec}
    # Agent turns are multi-hop (model -> tool -> model); allow a longer default ceiling.
    agent_timeout = timeout or max(gateway_timeout(), 90.0)
    status, text = _http_post_json(base + "/run-agent", headers, body, agent_timeout)
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        raise GatewayError("bad-response", f"gateway returned non-JSON (status {status})")
    if not isinstance(data, dict) or not data.get("ok"):
        err = (data or {}).get("error") or {}
        raise GatewayError(
            str(err.get("code") or f"http-{status}"),
            str(err.get("message") or text[:200]),
        )
    return str(data.get("text") or "")


class ChatGateway(BaseChatModel):
    """A LangChain chat model backed by the beans-ai warm Claude-subscription gateway.

    Drop-in for ``ChatGoogleGenerativeAI`` on the ``PROMPT | llm | JsonOutputParser`` +
    ``.invoke()`` path the Timonel graph uses. SystemMessages become the gateway ``system``
    field; the remaining messages are concatenated into ``prompt``. ``temperature`` / ``model``
    are accepted for signature parity and ignored (the subscription model is fixed on the box).
    """

    gateway_url: str = ""
    shared_secret: str = ""
    timeout: float = DEFAULT_TIMEOUT
    temperature: float = 0.2
    model: str = "claude-subscription"

    @property
    def _llm_type(self) -> str:
        return "beans-gateway"

    @property
    def _identifying_params(self) -> dict:
        return {"gateway_url": self.gateway_url or gateway_url(), "model": self.model}

    @staticmethod
    def _split(messages: list[BaseMessage]) -> tuple[str, str]:
        system_parts: list[str] = []
        prompt_parts: list[str] = []
        for m in messages:
            content = m.content if isinstance(m.content, str) else str(m.content)
            if isinstance(m, SystemMessage):
                system_parts.append(content)
            else:
                prompt_parts.append(content)
        return "\n\n".join(p for p in system_parts if p), "\n\n".join(p for p in prompt_parts if p)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        system, prompt = self._split(messages)
        data = call_gateway(
            system,
            prompt,
            url=self.gateway_url or None,
            secret=self.shared_secret or None,
            timeout=self.timeout,
        )
        text = data.get("text")
        if text is None and "json" in data:
            text = json.dumps(data["json"])
        text = text or ""
        # Carve the first balanced JSON object out of a prose-wrapped reply so the downstream
        # JsonOutputParser sees clean JSON (output-shape-drift mitigation; a reply with no object
        # is passed through untouched for non-JSON uses).
        carved = _carve_json_text(text)
        message = AIMessage(content=carved)
        return ChatResult(generations=[ChatGeneration(message=message)])


def make_gateway_llm(temperature: float = 0.2) -> ChatGateway:
    """Factory mirroring llm.get_llm(): a ChatGateway configured from the environment."""
    return ChatGateway(
        gateway_url=gateway_url(),
        shared_secret=shared_secret(),
        timeout=gateway_timeout(),
        temperature=temperature,
    )


class SafeDefaultChatModel(BaseChatModel):
    """The never-hard-fail floor for Timonel's model path (spec 005, per-call fallback).

    When the gateway is down AND Gemini is unavailable, this returns a minimal, parseable JSON
    object (`{}`). The graph nodes are wrapped in `safe_node`, and the read/resolver/decomposer
    agents read fields with `.get(...)`, so an empty object degrades Timonel to a clarify / safe
    reply rather than a crash: an agent that still subscripts a missing key (the router) raises,
    but that raise is caught by its own try/except and the `safe_node` backstop and resolves to
    the AMBIGUOUS/clarify path — never a hard failure. It is the last link in the with_fallbacks
    chain, never the primary."""

    safe_json: str = "{}"

    @property
    def _llm_type(self) -> str:
        return "beans-safe-default"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.safe_json))])


def validate_against(model_cls, data: dict):
    """Re-validate a gateway dict against an agent's Pydantic schema (spec 005, per-call
    re-validation). Returns the validated model on success; raises the pydantic ValidationError
    on failure so the caller can fall back. Works with both pydantic v1 and v2 model classes."""
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(data)
    return model_cls.parse_obj(data)  # pydantic v1
