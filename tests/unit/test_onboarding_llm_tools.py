"""Unit tests for ``backend.services.onboarding_llm_tools`` (M3.2 + M3.3).

Covers:
- Pydantic input validation for each of the six tool argument models.
- ``TOOL_REGISTRY`` shape: exactly six entries, expected names.
- Each executor returns a result of the expected variant.

The capture executors are exercised against a mocked repo so this file
stays DB-free; the integration of the real persistence layer lives in
``test_pending_onboarding_repo.py`` and ``test_onboarding_dispatcher.py``.
"""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.services.onboarding_llm_tools import (
    TOOL_REGISTRY,
    CaptureBusinessNameArgs,
    CaptureCurrencyArgs,
    CaptureLanguageArgs,
    CaptureOwnerNameArgs,
    CapturePhoneArgs,
    ConfirmAndCreateTenantArgs,
    ToolConflict,
    ToolHardFail,
    ToolOk,
    execute_capture_business_name,
    execute_capture_currency,
    execute_capture_language,
    execute_capture_owner_name,
    execute_capture_phone,
    execute_confirm_and_create_tenant,
)


class _StubRepo:
    """In-memory stand-in for PendingOnboardingRepository used by execs."""

    def __init__(self):
        self.merges: list[tuple[str, dict]] = []

    def merge_state(self, email: str, partial: dict):
        self.merges.append((email, partial))
        return partial

    def phone_in_use_by_other_pending(self, phone, current_email):
        return False


@pytest.fixture
def stub_repo():
    repo = _StubRepo()
    with patch(
        "backend.services.onboarding_llm_tools._get_repo",
        return_value=repo,
    ), patch(
        "backend.services.onboarding_llm_tools._phone_in_tenants",
        return_value=False,
    ):
        yield repo


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------


class TestCaptureBusinessNameArgs:
    def test_accepts_valid_name(self):
        args = CaptureBusinessNameArgs(name="Cafe del Centro")
        assert args.name == "Cafe del Centro"

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            CaptureBusinessNameArgs(name="")

    def test_rejects_too_long_name(self):
        with pytest.raises(ValidationError):
            CaptureBusinessNameArgs(name="x" * 121)

    def test_accepts_max_length_name(self):
        args = CaptureBusinessNameArgs(name="x" * 120)
        assert len(args.name) == 120


class TestCapturePhoneArgs:
    def test_accepts_intl_phone(self):
        args = CapturePhoneArgs(phone="+5491153695627")
        assert args.phone == "+5491153695627"

    def test_rejects_empty_phone(self):
        with pytest.raises(ValidationError):
            CapturePhoneArgs(phone="")

    def test_rejects_too_long_phone(self):
        with pytest.raises(ValidationError):
            CapturePhoneArgs(phone="+" + "1" * 20)


class TestCaptureCurrencyArgs:
    @pytest.mark.parametrize("currency", ["USD", "ARS", "EUR", "AUD"])
    def test_accepts_supported_currencies(self, currency):
        args = CaptureCurrencyArgs(currency=currency)
        assert args.currency == currency

    @pytest.mark.parametrize("currency", ["BRL", "GBP", "usd", "", "JPY"])
    def test_rejects_unsupported_currencies(self, currency):
        with pytest.raises(ValidationError):
            CaptureCurrencyArgs(currency=currency)


class TestCaptureLanguageArgs:
    @pytest.mark.parametrize("language", ["es", "en"])
    def test_accepts_supported_languages(self, language):
        args = CaptureLanguageArgs(language=language)
        assert args.language == language

    @pytest.mark.parametrize("language", ["pt", "fr", "ES", "EN", ""])
    def test_rejects_unsupported_languages(self, language):
        with pytest.raises(ValidationError):
            CaptureLanguageArgs(language=language)


class TestCaptureOwnerNameArgs:
    def test_accepts_valid_name(self):
        args = CaptureOwnerNameArgs(name="Dario")
        assert args.name == "Dario"

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            CaptureOwnerNameArgs(name="")

    def test_rejects_too_long_name(self):
        with pytest.raises(ValidationError):
            CaptureOwnerNameArgs(name="x" * 121)


class TestConfirmAndCreateTenantArgs:
    def test_takes_no_args(self):
        # Must instantiate without parameters; the executor reads state.
        args = ConfirmAndCreateTenantArgs()
        assert args.model_dump() == {}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_has_six_entries(self):
        assert len(TOOL_REGISTRY) == 6

    def test_has_expected_names(self):
        expected = {
            "capture_business_name",
            "capture_phone",
            "capture_currency",
            "capture_language",
            "capture_owner_name",
            "confirm_and_create_tenant",
        }
        assert set(TOOL_REGISTRY.keys()) == expected

    def test_each_entry_is_pair_of_model_and_callable(self):
        for name, entry in TOOL_REGISTRY.items():
            assert len(entry) == 2, f"{name} entry is not a 2-tuple"
            args_model, executor = entry
            assert isinstance(args_model, type), f"{name} args_model is not a class"
            assert callable(executor), f"{name} executor is not callable"


# ---------------------------------------------------------------------------
# Executor stubs
# ---------------------------------------------------------------------------


SESSION_EMAIL = "test-user@gmail.com"


class TestExecutorStubs:
    def test_business_name_returns_tool_ok(self, stub_repo):
        result = execute_capture_business_name(
            SESSION_EMAIL,
            CaptureBusinessNameArgs(name="Cafe del Centro"),
        )
        assert isinstance(result, ToolOk)
        assert result.ok is True
        assert result.captured == {"business_name": "Cafe del Centro"}
        assert "Cafe del Centro" in result.label_es
        # Accented Spanish: "Anoté" not "Anote".
        assert "Anoté" in result.label_es

    def test_phone_returns_tool_ok(self, stub_repo):
        result = execute_capture_phone(
            SESSION_EMAIL,
            CapturePhoneArgs(phone="+5491153695627"),
        )
        assert isinstance(result, ToolOk)
        assert result.captured == {"phone": "+5491153695627"}
        assert "+5491153695627" in result.label_es
        assert "Anoté" in result.label_es

    def test_phone_rejects_no_plus_prefix(self, stub_repo):
        result = execute_capture_phone(
            SESSION_EMAIL,
            CapturePhoneArgs(phone="5491153695627"),
        )
        assert isinstance(result, ToolConflict)
        assert result.error == "validation_error"

    def test_currency_returns_tool_ok(self, stub_repo):
        result = execute_capture_currency(
            SESSION_EMAIL,
            CaptureCurrencyArgs(currency="ARS"),
        )
        assert isinstance(result, ToolOk)
        assert result.captured == {"currency": "ARS"}
        assert "ARS" in result.label_es
        assert "Anoté" in result.label_es

    def test_language_returns_tool_ok(self, stub_repo):
        result = execute_capture_language(
            SESSION_EMAIL,
            CaptureLanguageArgs(language="es"),
        )
        assert isinstance(result, ToolOk)
        assert result.captured == {"language": "es"}
        assert "es" in result.label_es
        assert "Anoté" in result.label_es

    def test_owner_name_returns_tool_ok(self, stub_repo):
        result = execute_capture_owner_name(
            SESSION_EMAIL,
            CaptureOwnerNameArgs(name="Dario"),
        )
        assert isinstance(result, ToolOk)
        assert result.captured == {"owner_name": "Dario"}
        assert "Dario" in result.label_es
        # Accented form for "dueño" must round-trip.
        assert "dueño" in result.label_es

    def test_capture_session_expired_returns_hard_fail(self):
        """If the pending row vanished, merge_state raises LookupError; the
        executor surfaces ``session_expired``."""

        class _MissingRepo:
            def merge_state(self, *_args, **_kwargs):
                raise LookupError("gone")

        with patch(
            "backend.services.onboarding_llm_tools._get_repo",
            return_value=_MissingRepo(),
        ):
            result = execute_capture_business_name(
                SESSION_EMAIL, CaptureBusinessNameArgs(name="X")
            )
        assert isinstance(result, ToolHardFail)
        assert result.error == "session_expired"

    def test_confirm_returns_session_expired_when_no_row(self):
        """With no pending row at all, confirm bails as ``session_expired``."""

        class _MissingRepo:
            def get(self, _email):
                return None

        with patch(
            "backend.services.onboarding_llm_tools._get_repo",
            return_value=_MissingRepo(),
        ):
            result = execute_confirm_and_create_tenant(
                SESSION_EMAIL, ConfirmAndCreateTenantArgs()
            )
        assert isinstance(result, ToolHardFail)
        assert result.error == "session_expired"

    def test_confirm_returns_validation_error_when_state_incomplete(self):
        """A pending row with holes returns ``validation_error``."""

        class _PartialRepo:
            def get(self, _email):
                return {"state": {"business_name": "X"}}

        with patch(
            "backend.services.onboarding_llm_tools._get_repo",
            return_value=_PartialRepo(),
        ):
            result = execute_confirm_and_create_tenant(
                SESSION_EMAIL, ConfirmAndCreateTenantArgs()
            )
        assert isinstance(result, ToolConflict)
        assert result.error == "validation_error"
