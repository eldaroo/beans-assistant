"""Tests for the `safe_node` decorator (T-002).

Covers:
- A wrapped node returns its normal delta on the happy path.
- A wrapped node never lets exceptions leak; instead it writes a typed
  state delta with class/node/msg/incident_id.
- Each documented exception shape resolves to the documented
  error_class.
- One unit test per real graph node confirms the safe wrapper applied
  in `graph.py` swallows a forced exception.
"""
from __future__ import annotations

import json
import logging

import pytest

from agents.safe_node import (
    ERROR_CLASSES,
    _classify,
    _new_incident_id,
    safe_node,
)


@pytest.mark.unit
class TestSafeNodeHappyPath:
    def test_returns_node_delta_unchanged_on_success(self):
        @safe_node("router")
        def node(state):
            return {"intent": "READ_ANALYTICS", "messages": []}

        delta = node({"phone": "+5491111"})
        assert delta == {"intent": "READ_ANALYTICS", "messages": []}
        assert "error" not in delta

    def test_preserves_function_name_and_docstring(self):
        @safe_node("router")
        def my_node(state):
            """Doc."""
            return {}

        assert my_node.__name__ == "my_node"
        assert my_node.__doc__ == "Doc."
        assert hasattr(my_node, "__wrapped__")


@pytest.mark.unit
class TestSafeNodeCatchesAllExceptions:
    def test_writes_error_state_instead_of_raising(self, caplog):
        @safe_node("router")
        def node(state):
            raise RuntimeError("boom")

        caplog.set_level(logging.ERROR)
        delta = node({"phone": "+5491111", "intent": None})

        assert "error" in delta
        err = delta["error"]
        assert err["node"] == "router"
        assert err["msg"] == "boom"
        assert err["class"] in ERROR_CLASSES
        assert err["incident_id"]
        assert isinstance(err["incident_id"], str)
        assert len(err["incident_id"]) >= 6

    def test_handles_none_state_safely(self):
        @safe_node("router")
        def node(state):
            raise ValueError("kaboom")

        delta = node(None)
        assert "error" in delta
        assert delta["error"]["node"] == "router"

    def test_emits_structured_log_line(self, caplog):
        @safe_node("write_agent")
        def node(state):
            raise ValueError("missing required field name")

        caplog.set_level(logging.ERROR, logger="agents.safe_node")
        node({"phone": "+5491111", "intent": "WRITE_OPERATION"})

        json_records = [
            r for r in caplog.records
            if r.name == "agents.safe_node"
        ]
        assert json_records, "expected at least one structured log record"

        # The line is one JSON object per exception.
        payload = json.loads(json_records[-1].getMessage())
        assert payload["event"] == "graph_node_exception"
        assert payload["node"] == "write_agent"
        assert payload["phone"] == "+5491111"
        assert payload["intent"] == "WRITE_OPERATION"
        assert payload["error_class"] in ERROR_CLASSES
        assert payload["incident_id"]
        assert payload["msg"] == "missing required field name"


@pytest.mark.unit
class TestClassificationHeuristic:
    def test_key_error_is_missing_field(self):
        assert _classify(KeyError("name")) == "missing_field"

    def test_pydantic_validation_error_is_missing_field(self):
        # Stand-in: pydantic ValidationError class name detection.
        class ValidationError(Exception):
            pass

        assert _classify(ValidationError("bad")) == "missing_field"

    def test_message_with_missing_field_phrase(self):
        assert _classify(ValueError("missing required field name")) == "missing_field"

    def test_unknown_product_phrase(self):
        assert _classify(RuntimeError("Product not found: prodcuo")) == "unknown_product"
        assert _classify(RuntimeError("Producto no encontrado")) == "unknown_product"
        assert _classify(RuntimeError("Unknown product foo")) == "unknown_product"

    def test_httpx_module_is_network(self):
        # Synthesize a class living under httpx so the module check fires
        # without requiring httpx to be installed.
        class FakeReadTimeout(Exception):
            pass

        FakeReadTimeout.__module__ = "httpx._exceptions"
        assert _classify(FakeReadTimeout("read timed out")) == "network"

    def test_connection_error_is_network(self):
        assert _classify(ConnectionError("connection refused")) == "network"

    def test_timeout_class_name_is_network(self):
        class ReadTimeout(Exception):
            pass

        assert _classify(ReadTimeout("slow")) == "network"

    def test_explicit_ambiguous_phrase(self):
        assert _classify(RuntimeError("ambiguous input candidate")) == "ambiguous_input"

    def test_default_falls_back_to_llm_unavailable(self):
        assert _classify(RuntimeError("something weird happened")) == "llm_unavailable"


@pytest.mark.unit
class TestIncidentId:
    def test_incident_id_is_short_and_unique(self):
        ids = {_new_incident_id() for _ in range(50)}
        assert len(ids) == 50
        for ident in ids:
            assert isinstance(ident, str)
            assert 6 <= len(ident) <= 16


@pytest.mark.unit
class TestSafeWrappersAppliedInGraph:
    """One forced-exception probe per real wrapped node.

    We monkeypatch the underlying business callable inside `graph.py` to
    raise, then call the wrapped function the graph would dispatch and
    assert the state delta is set without re-raising.
    """

    @pytest.mark.parametrize(
        "node_name",
        ["decomposer", "router", "resolver", "read_agent", "write_agent"],
    )
    def test_each_node_is_wrapped(self, node_name):
        # The wrapped versions live in graph.py as `_<node>_wrapped` to
        # keep the public names available for tests that import the
        # underlying callables.
        from graph import _build_safe_wrappers

        wrappers = _build_safe_wrappers(
            decomposer=_raising("decomposer"),
            router=_raising("router"),
            resolver=_raising("resolver"),
            read_agent=_raising("read_agent"),
            write_agent=_raising("write_agent"),
        )
        assert node_name in wrappers
        delta = wrappers[node_name]({"phone": "+5491111", "intent": None})
        assert "error" in delta
        assert delta["error"]["node"] == node_name
        assert delta["error"]["incident_id"]


def _raising(label):
    def fn(state):
        raise RuntimeError(f"forced failure in {label}")

    return fn


@pytest.mark.unit
class TestSentryTagging:
    """T-006: when sentry_sdk is importable, safe_node tags the event with
    error_class / node / incident_id and captures the exception. When
    sentry_sdk is not installed, safe_node still works without raising.
    """

    def test_sentry_tags_set_when_sdk_importable(self, monkeypatch):
        """Inject a fake sentry_sdk into sys.modules and verify tags fire."""
        import sys
        from types import SimpleNamespace

        calls = {"tags": [], "captures": 0}

        def set_tag(key, value):
            calls["tags"].append((key, value))

        def capture_exception(exc):
            calls["captures"] += 1

        fake = SimpleNamespace(set_tag=set_tag, capture_exception=capture_exception)
        monkeypatch.setitem(sys.modules, "sentry_sdk", fake)

        @safe_node("router")
        def node(state):
            raise RuntimeError("boom")

        delta = node({"phone": "+5491111", "intent": None})

        assert delta["error"]["class"] in ERROR_CLASSES
        keys = {k for k, _ in calls["tags"]}
        assert "error_class" in keys
        assert "node" in keys
        assert "incident_id" in keys
        assert calls["captures"] == 1

    def test_no_op_when_sentry_sdk_missing(self, monkeypatch):
        """Without sentry_sdk on the path, safe_node still succeeds."""
        import sys

        # Force the import path to fail.
        monkeypatch.setitem(sys.modules, "sentry_sdk", None)

        @safe_node("router")
        def node(state):
            raise RuntimeError("boom")

        delta = node({"phone": "+5491111"})
        assert "error" in delta
