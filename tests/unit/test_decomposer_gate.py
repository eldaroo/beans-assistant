"""
Pure regex gate tests for the decomposer.

`should_decompose` is the pre-LLM gate that decides whether to invoke the
decomposer LLM at all. ADR-pinned cases live here; do not relax without
updating the ADR. Per ADR Decision 2:

- LIST_SEPARATOR fires when the input contains 3+ items separated by `,`,
  ` y `, or newline. Two items by themselves do NOT trigger.
- ACTION_VERBS fires when 2+ distinct verb lemmas appear.
- If neither matches, the gate returns False and the decomposer skips the
  LLM call entirely.
"""
import pytest

from agents.decomposer import should_decompose


@pytest.mark.unit
class TestPassThrough:
    """Single-intent inputs must NOT dispatch the decomposer LLM."""

    def test_simple_sale(self):
        assert should_decompose("vendi 5 medias") is False

    def test_simple_question(self):
        assert should_decompose("cuanto stock tengo") is False

    def test_greeting_hola(self):
        assert should_decompose("hola") is False

    def test_short_ack_ok(self):
        assert should_decompose("ok") is False

    def test_two_items_no_verb(self):
        # ADR-pinned: only two items so LIST_SEPARATOR (which demands 3+) does
        # not trigger. No action verbs either, so MULTI_VERB also passes.
        assert should_decompose("manzanas, peras") is False

    def test_empty_input(self):
        assert should_decompose("") is False

    def test_none_safe(self):
        # Defensive: callers may hand None when state is half-built.
        assert should_decompose(None) is False  # type: ignore[arg-type]


@pytest.mark.unit
class TestListSeparatorTrigger:
    """LIST_SEPARATOR pattern must catch 3+ comma/`y`/newline-separated items."""

    def test_vendo_lista_y_final(self):
        assert should_decompose("vendo medias, pantaletas y soquetes") is True

    def test_three_capitalized_nouns(self):
        assert should_decompose("Peras, Manzanas, Bananas") is True

    def test_creo_three_items(self):
        assert should_decompose("creo medias, peras, bananas") is True

    def test_newline_separated_list(self):
        assert should_decompose("medias\npantaletas\nsoquetes") is True


@pytest.mark.unit
class TestMultiVerbTrigger:
    """ACTION_VERBS must trigger when 2+ distinct verb lemmas appear."""

    def test_vendi_y_compre(self):
        assert should_decompose("vendi 5 medias y compre 3 peras") is True

    def test_registro_y_vendo(self):
        # Two distinct lemmas from the ADR closed list ("registro", "vendo").
        assert should_decompose(
            "registro gasto de envios y vendo soquetes"
        ) is True

    def test_compre_y_anula(self):
        assert should_decompose(
            "compre 5 peras y anula la ultima venta"
        ) is True

    def test_repeated_same_verb_does_not_trigger_multi_verb(self):
        # Same verb twice should not fire MULTI_VERB on its own. But this
        # particular phrasing also lacks a 3+ list, so the gate stays False.
        assert should_decompose("vendi medias vendi pantaletas") is False
