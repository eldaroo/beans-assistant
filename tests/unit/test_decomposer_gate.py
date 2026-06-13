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


@pytest.mark.unit
class TestCreateProductsGuard:
    """A single product-creation action over a list is NOT multi-intent.

    Per ARCHITECTURE D-001 a multi-product REGISTER_PRODUCT is owned by the
    router + expander. The decomposer must keep such a turn whole instead of
    fragmenting it into per-item sub-inputs (which the splitter LLM then
    re-infers as per-item SALES, the production failure these cases pin).
    """

    def test_agregar_productos_with_named_list_passes_through(self):
        # The exact production failure: "agregar 3 productos ... estoy
        # vendiendo cascos de moto, zapatillas nike y pulseras de cafe" was
        # fragmented into three failed SALE sub-inputs. It must stay whole.
        assert should_decompose(
            "podes agregar unos 3 productos a esta tabla. Estoy vendiendo "
            "cascos de moto, zapatillas nike y pulseras de cafe"
        ) is False

    def test_agregar_n_productos_colon_list(self):
        assert should_decompose(
            "agregar 3 productos: cascos de moto, zapatillas nike y pulseras"
        ) is False

    def test_crear_productos_list(self):
        assert should_decompose(
            "crear productos: peras verdes, manzanas rojas, bananas"
        ) is False

    def test_cargar_articulos_al_catalogo(self):
        assert should_decompose(
            "cargar articulos al catalogo: medias, peras, bananas"
        ) is False

    def test_agregar_nuevas_variant_list(self):
        # "nuevas" forces REGISTER_PRODUCT downstream; the expander fans out
        # the color list. Keep it whole so the expander can run.
        assert should_decompose(
            "agregar nuevas pulseras: arcoiris, fucsias, pasteles"
        ) is False

    def test_register_products_english(self):
        assert should_decompose(
            "add products: moto helmets, nike sneakers, coffee bracelets"
        ) is False

    def test_sale_list_still_decomposes(self):
        # Guard must NOT swallow a genuine multi-item sale list (no create
        # verb / object). Existing behavior preserved.
        assert should_decompose("vendo medias, pantaletas y soquetes") is True

    def test_creo_bare_names_still_decomposes(self):
        # No catalog object or "nuevo" signal, just "creo" + bare names: the
        # guard does not fire, so the list trigger still splits it (each
        # "creo X" is a self-contained creation the router handles per item).
        # ADR-pinned in TestListSeparatorTrigger; re-asserted here.
        assert should_decompose("creo medias, peras, bananas") is True

    def test_multi_action_with_create_still_decomposes(self):
        # A genuine multi-action turn (distinct verbs) wins over the guard:
        # "vendo" + "compre" are two actions regardless of any create phrasing.
        assert should_decompose(
            "vendo medias y compre 3 productos nuevos"
        ) is True
