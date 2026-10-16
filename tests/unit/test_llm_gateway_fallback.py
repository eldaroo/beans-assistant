"""Per-call fallback tests (spec 005, M4). Timonel never hard-fails on the model path: a gateway
error falls back to Gemini (during cutover) and finally to a safe deterministic response. No
network — the gateway transport is monkeypatched to fail, and the Gemini fallback is an injected
stand-in."""

import os
import sys
from typing import Any, Optional

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import llm as L  # noqa: E402
import llm_gateway as G  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402


class _FakeModel(BaseChatModel):
    tag: str = "fake"

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.tag))])


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BEANS_AI_SHARED_SECRET", "unit-secret")
    monkeypatch.delenv("TIMONEL_LLM_FALLBACK", raising=False)


def _break_gateway(monkeypatch):
    def boom(*a, **k):
        raise G.GatewayError("unreachable", "down")

    monkeypatch.setattr(G, "_http_post_json", boom)


def test_safe_default_returns_parseable_json():
    m = G.SafeDefaultChatModel()
    out = m.invoke([HumanMessage(content="x")])
    assert out.content == "{}"


def test_validate_against_ok_and_fail():
    from pydantic import BaseModel

    class Intent(BaseModel):
        intent: str
        confidence: float

    ok = G.validate_against(Intent, {"intent": "READ", "confidence": 0.9})
    assert ok.intent == "READ"
    with pytest.raises(Exception):
        G.validate_against(Intent, {"intent": "READ"})  # missing confidence


def test_gateway_failure_falls_back_to_safe_default(monkeypatch):
    _break_gateway(monkeypatch)
    chain = G.make_gateway_llm().with_fallbacks([G.SafeDefaultChatModel()])
    out = chain.invoke([HumanMessage(content="hola")])
    assert out.content == "{}"


def test_with_fallbacks_uses_gemini_when_key_present(monkeypatch):
    _break_gateway(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")
    chain = L._with_fallbacks(G.make_gateway_llm(), lambda: _FakeModel(tag="gemini-used"))
    out = chain.invoke([HumanMessage(content="hola")])
    assert out.content == "gemini-used"


def test_with_fallbacks_safe_default_when_no_gemini_key(monkeypatch):
    _break_gateway(monkeypatch)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    chain = L._with_fallbacks(G.make_gateway_llm(), lambda: _FakeModel(tag="should-not-be-built"))
    out = chain.invoke([HumanMessage(content="hola")])
    assert out.content == "{}"


def test_fallback_can_be_disabled(monkeypatch):
    monkeypatch.setenv("TIMONEL_LLM_FALLBACK", "off")
    primary = G.make_gateway_llm()
    assert L._with_fallbacks(primary, lambda: _FakeModel()) is primary


def test_working_gateway_does_not_fall_back(monkeypatch):
    monkeypatch.setattr(G, "_http_post_json", lambda *a, **k: (200, '{"ok":true,"path":"warm","text":"real"}'))
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")
    chain = L._with_fallbacks(G.make_gateway_llm(), lambda: _FakeModel(tag="gemini"))
    out = chain.invoke([HumanMessage(content="hola")])
    assert out.content == "real"
