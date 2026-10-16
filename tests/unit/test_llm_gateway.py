"""Offline tests for llm_gateway.py (spec 005). No real gateway, no token: the single network
seam (_http_post_json) is monkeypatched, so the client, the LangChain model, and the full
`PROMPT | ChatGateway | JsonOutputParser` swap path are exercised deterministically."""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import llm_gateway as G  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # noqa: E402
from langchain_core.output_parsers import JsonOutputParser  # noqa: E402
from langchain_core.prompts import ChatPromptTemplate  # noqa: E402


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("BEANS_AI_SHARED_SECRET", "unit-secret")
    monkeypatch.setenv("BEANS_AI_GATEWAY_URL", "https://gw.example/")


def _stub_transport(monkeypatch, status, body_obj, capture=None):
    def fake(url, headers, body, timeout):
        if capture is not None:
            capture["url"] = url
            capture["headers"] = headers
            capture["payload"] = json.loads(body.decode())
            capture["timeout"] = timeout
        return status, json.dumps(body_obj)

    monkeypatch.setattr(G, "_http_post_json", fake)


def test_call_gateway_happy_text(monkeypatch):
    cap = {}
    _stub_transport(monkeypatch, 200, {"ok": True, "path": "warm", "text": "hola"}, cap)
    data = G.call_gateway("SYS", "frase", max_tokens=256)
    assert data["text"] == "hola"
    assert data["path"] == "warm"
    # request shape
    assert cap["url"] == "https://gw.example/run"
    assert cap["headers"]["authorization"] == "Bearer unit-secret"
    assert cap["payload"] == {"system": "SYS", "prompt": "frase", "max_tokens": 256}


def test_call_gateway_json_mode(monkeypatch):
    cap = {}
    _stub_transport(monkeypatch, 200, {"ok": True, "path": "warm", "json": {"intent": "READ"}}, cap)
    data = G.call_gateway("S", "p", json_schema={"intent": "string"})
    assert data["json"] == {"intent": "READ"}
    assert cap["payload"]["json_schema"] == {"intent": "string"}


def test_call_gateway_ok_false_raises_with_code(monkeypatch):
    _stub_transport(monkeypatch, 502, {"ok": False, "error": {"code": "model-error", "message": "boom"}})
    with pytest.raises(G.GatewayError) as e:
        G.call_gateway("S", "p")
    assert e.value.code == "model-error"
    assert "boom" in e.value.message


def test_call_gateway_no_secret_raises(monkeypatch):
    monkeypatch.delenv("BEANS_AI_SHARED_SECRET", raising=False)
    with pytest.raises(G.GatewayError) as e:
        G.call_gateway("S", "p")
    assert e.value.code == "no-secret"


def test_call_gateway_non_json_body(monkeypatch):
    monkeypatch.setattr(G, "_http_post_json", lambda *a, **k: (200, "<html>nope</html>"))
    with pytest.raises(G.GatewayError) as e:
        G.call_gateway("S", "p")
    assert e.value.code == "bad-response"


def test_call_gateway_unreachable(monkeypatch):
    def boom(*a, **k):
        raise G.GatewayError("unreachable", "connection refused")

    monkeypatch.setattr(G, "_http_post_json", boom)
    with pytest.raises(G.GatewayError) as e:
        G.call_gateway("S", "p")
    assert e.value.code == "unreachable"


def test_split_separates_system_and_prompt():
    system, prompt = G.ChatGateway._split(
        [SystemMessage(content="eres router"), HumanMessage(content="cuanto vendi"), AIMessage(content="ctx")]
    )
    assert system == "eres router"
    assert "cuanto vendi" in prompt and "ctx" in prompt


def test_chatgateway_invoke_returns_text(monkeypatch):
    _stub_transport(monkeypatch, 200, {"ok": True, "path": "warm", "text": '{"intent":"GREETING"}'})
    llm = G.make_gateway_llm()
    msg = llm.invoke([SystemMessage(content="router"), HumanMessage(content="hola")])
    assert isinstance(msg, AIMessage)
    assert msg.content == '{"intent":"GREETING"}'


def test_full_lcel_chain_parses_json_unchanged(monkeypatch):
    # Proves the swap is transparent: the existing PROMPT | llm | JsonOutputParser shape yields
    # the same dict it would from Gemini, with no schema change.
    # The gateway returns clean JSON (the prompts instruct it to), exactly as Gemini did, so the
    # existing JsonOutputParser coerces it unchanged. A fenced ```json block is also accepted,
    # which the parser handles as it did for Gemini.
    _stub_transport(
        monkeypatch,
        200,
        {"ok": True, "path": "warm", "text": '```json\n{"intent":"REGISTER_SALE","confidence":0.92}\n```'},
    )
    prompt = ChatPromptTemplate.from_messages(
        [("system", "Sos el router de Timonel. Devolvé JSON."), ("human", "{input}")]
    )
    chain = prompt | G.make_gateway_llm() | JsonOutputParser()
    result = chain.invoke({"input": "vendí una tabla a 400"})
    assert result == {"intent": "REGISTER_SALE", "confidence": 0.92}
