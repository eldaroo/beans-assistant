"""Tests for optional cache dependencies."""

import importlib
import sys

import pytest


@pytest.mark.unit
def test_backend_cache_imports_without_redis(monkeypatch):
    """backend.cache should still import when redis is unavailable."""
    monkeypatch.setitem(sys.modules, "redis", None)
    sys.modules.pop("backend.cache", None)

    module = importlib.import_module("backend.cache")

    assert hasattr(module, "get_cache")
    assert module.REDIS_ENABLED is True or module.REDIS_ENABLED is False
