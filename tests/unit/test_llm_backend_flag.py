"""Tests for the TIMONEL_LLM_BACKEND dispatch in llm.py (spec 005, M3). No network: a gateway
backend returns a ChatGateway (no Gemini key needed); the Gemini default is constructed with a
dummy key (no API call happens at construction)."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import llm as L  # noqa: E402
from llm_gateway import ChatGateway  # noqa: E402
from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: E402


def _primary(model):
    """On the gateway path get_llm wraps the ChatGateway in with_fallbacks (M4), so the returned
    object is a RunnableWithFallbacks whose `.runnable` is the primary ChatGateway. Unwrap it."""
    return getattr(model, "runnable", model)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("TIMONEL_LLM_BACKEND"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BEANS_AI_SHARED_SECRET", "unit-secret")
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-key-for-construction")


def test_resolve_backend_defaults_to_gemini(monkeypatch):
    assert L.resolve_backend() == "gemini"


def test_resolve_backend_global_flag(monkeypatch):
    monkeypatch.setenv("TIMONEL_LLM_BACKEND", "gateway")
    assert L.resolve_backend() == "gateway"


def test_resolve_backend_per_tenant_override(monkeypatch):
    monkeypatch.setenv("TIMONEL_LLM_BACKEND", "gemini")
    monkeypatch.setenv("TIMONEL_LLM_BACKEND_CAFE_RAMA", "gateway")
    assert L.resolve_backend("cafe-rama") == "gateway"  # non-alnum normalized to _
    assert L.resolve_backend("other") == "gemini"


def test_get_llm_gateway_backend_returns_chatgateway(monkeypatch):
    monkeypatch.setenv("TIMONEL_LLM_BACKEND", "gateway")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)  # gateway path must not need a Gemini key
    assert isinstance(_primary(L.get_llm()), ChatGateway)
    assert isinstance(_primary(L.get_llm_cheap()), ChatGateway)


def test_get_llm_gemini_default_returns_gemini(monkeypatch):
    assert isinstance(L.get_llm(), ChatGoogleGenerativeAI)
    assert isinstance(L.get_llm_cheap(), ChatGoogleGenerativeAI)


def test_get_llm_for_tools_stays_gemini_even_on_gateway(monkeypatch):
    monkeypatch.setenv("TIMONEL_LLM_BACKEND", "gateway")
    assert isinstance(L.get_llm_for_tools(), ChatGoogleGenerativeAI)


def test_per_tenant_gateway_without_global(monkeypatch):
    monkeypatch.setenv("TIMONEL_LLM_BACKEND_RAMA", "gateway")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert isinstance(_primary(L.get_llm("rama")), ChatGateway)


def test_get_llm_backend_pin_overrides_resolution(monkeypatch):
    # The graph cache pins a backend; get_llm(backend=...) must honor it regardless of the flag.
    monkeypatch.setenv("TIMONEL_LLM_BACKEND", "gemini")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert isinstance(_primary(L.get_llm(backend="gateway")), ChatGateway)
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")
    monkeypatch.setenv("TIMONEL_LLM_BACKEND", "gateway")
    assert isinstance(L.get_llm(backend="gemini"), ChatGoogleGenerativeAI)


def test_chat_service_graph_cache_keys_by_backend(monkeypatch):
    # The per-tenant cutover is only real if the cached graph routes by backend (council BLOCKER).
    from backend.services import chat_service as cs

    built = []
    monkeypatch.setattr(cs, "create_business_agent_graph", lambda backend=None: built.append(backend) or f"graph:{backend}")
    cs.ChatService._graphs = {}
    g_gateway = cs.ChatService._get_graph("gateway")
    g_gemini = cs.ChatService._get_graph("gemini")
    g_gateway_again = cs.ChatService._get_graph("gateway")
    assert g_gateway == "graph:gateway"
    assert g_gemini == "graph:gemini"
    assert g_gateway is g_gateway_again or g_gateway == g_gateway_again  # cached, not rebuilt
    assert built == ["gateway", "gemini"]  # two builds, the repeat gateway call hit the cache


class _RaiseAfter:
    def invoke(self, *a, **k):
        raise RuntimeError("stop here; we only assert the backend was resolved")


def test_invoke_graph_resolves_backend_per_tenant(monkeypatch):
    # _invoke_graph must resolve the backend from the tenant phone and pass it to _get_graph. The
    # phone "+549..." normalizes (non-alnum -> _) to the env key below (leading + becomes _).
    from backend.services import chat_service as cs

    monkeypatch.setenv("TIMONEL_LLM_BACKEND__5491100000000", "gateway")
    seen = {}

    def fake_get_graph(c, backend=None):
        seen["backend"] = backend
        return _RaiseAfter()

    monkeypatch.setattr(cs.ChatService, "_get_graph", classmethod(fake_get_graph))
    # graph.invoke raises our sentinel after _get_graph has already recorded the backend; we only
    # assert the routing, so swallow it.
    try:
        cs.ChatService._invoke_graph(phone="+5491100000000", message="hola")
    except RuntimeError:
        pass
    assert seen.get("backend") == "gateway"
