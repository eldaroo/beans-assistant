"""Unit tests for ``backend.services.onboarding_llm_prompt`` (M3.2).

Covers:
- The rendered prompt contains the persona ("Timonel") and the injected
  Google name + email.
- The banned-vocabulary list (rule 10 of beans-voice-and-microcopy) is
  present (at least three banned words appear).
- ``state_json`` shows up correctly when state is non-empty.
- The prompt is under ~800 tokens (rough check: ``len(prompt) < 4000``).
"""

import json

from backend.services.onboarding_llm_prompt import build_system_prompt


def _basic_prompt(state=None, google_name="Dario", user_email="dario@gmail.com"):
    return build_system_prompt(state or {}, google_name, user_email)


class TestPersonaAndIdentity:
    def test_contains_timonel_persona(self):
        prompt = _basic_prompt()
        assert "Timonel" in prompt

    def test_injects_google_name(self):
        prompt = _basic_prompt(google_name="Maria Sol")
        assert "Maria Sol" in prompt

    def test_injects_user_email(self):
        prompt = _basic_prompt(user_email="maria@gmail.com")
        assert "maria@gmail.com" in prompt


class TestBannedVocabulary:
    def test_includes_at_least_three_banned_words(self):
        prompt = _basic_prompt()
        # Three randomly chosen banned tokens from rule 10.
        for banned in ("mágicamente", "simplemente", "¡Bienvenido!"):
            assert banned in prompt, f"banned token missing from prompt: {banned}"

    def test_includes_em_dash_guard(self):
        prompt = _basic_prompt()
        assert "em-dash" in prompt


class TestStateInjection:
    def test_empty_state_renders_empty_object(self):
        prompt = _basic_prompt(state={})
        assert "{}" in prompt

    def test_partial_state_appears_as_json(self):
        state = {"business_name": "Café del Centro"}
        prompt = _basic_prompt(state=state)
        # The renderer uses ``ensure_ascii=False`` so accents survive
        # round-trip without escapes.
        assert "Café del Centro" in prompt
        # And the value sits inside a JSON object structure.
        assert '"business_name"' in prompt

    def test_state_is_valid_json_substring(self):
        state = {"business_name": "Cafe", "currency": "ARS"}
        prompt = _basic_prompt(state=state)
        # Round-trip the embedded JSON to make sure it is well-formed.
        # Find the first '{' after "Datos ya anotados:" and parse it.
        marker = "Datos ya anotados:"
        idx = prompt.find(marker)
        assert idx >= 0
        # Locate the JSON object on that line.
        line = prompt[idx + len(marker):].splitlines()[0].strip()
        parsed = json.loads(line)
        assert parsed == {"business_name": "Cafe", "currency": "ARS"}


class TestSize:
    def test_prompt_is_short(self):
        prompt = _basic_prompt(
            state={"business_name": "Cafe del Centro", "phone": "+5491153695627"}
        )
        # 4000 chars is a comfortable proxy for <800 tokens.
        assert len(prompt) < 4000

    def test_prompt_has_no_em_dashes_in_static_copy(self):
        # Em-dashes are banned across the codebase; the system prompt
        # references the term "em-dash" verbatim but must not contain
        # the actual character.
        prompt = _basic_prompt()
        assert "—" not in prompt
