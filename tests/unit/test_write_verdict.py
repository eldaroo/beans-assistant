"""The server-computed auto verdict (spec 007 M3, AC8 / AC8b, D-040/D-041/D-042).

Pure tests, no DB: the verdict is the proof that a write is safe to auto-post, and it must
be unfoolable by tenant text or a hijacked model. Each falsifying case AC8b names drives
auto=False; the one obvious, grounded, single-candidate, reversible case drives auto=True.
"""
from backend.services import write_verdict as wv


def test_number_tokens_extracts_and_canonicalizes():
    toks = wv.number_tokens("vendí 2 tablas por 400 y gasté 1.500")
    assert "2" in toks
    assert "400" in toks
    assert "1500" in toks  # es thousands separator stripped


def test_numeral_is_grounded_matches_the_spoken_number():
    toks = wv.number_tokens("una venta por 400 de una tabla")
    assert wv.numeral_is_grounded(400, toks) is True
    assert wv.numeral_is_grounded(400.0, toks) is True
    assert wv.numeral_is_grounded(500, toks) is False  # a number the operator never said


def test_grounding_does_not_cross_scale_decimal_vs_integer():
    # Council (Tamir/Edut/Amelia): a staged 1.5 must NOT ground against an utterance "15",
    # and a staged 15 must not ground against "1.5". Parsed numerically, not by stripped digits.
    assert wv.numeral_is_grounded(1.5, wv.parse_numbers("vendí 15")) is False
    assert wv.numeral_is_grounded(15, wv.parse_numbers("a 1.5")) is False
    # es-thousands vs the real value still grounds correctly.
    assert wv.numeral_is_grounded(1500, wv.parse_numbers("por 1.500")) is True
    assert wv.numeral_is_grounded(1500, wv.parse_numbers("por 1,500")) is True
    assert wv.numeral_is_grounded(12.5, wv.parse_numbers("a 12,50")) is True


def test_bare_confirmation_is_detected():
    for s in ["ok", "dale", "sí", "si", "listo", "  Dale ", "confirmo"]:
        assert wv.is_bare_confirmation(s) is True
    assert wv.is_bare_confirmation("vendí una tabla por 400") is False


# ── AC8: the obvious, grounded, single-candidate, reversible write auto-posts ────────

def test_obvious_grounded_reversible_sale_auto_posts():
    v = wv.compute_verdict(
        operation_type="REGISTER_SALE",
        utterance="registrá una venta por 400 de una tabla",
        grounded_amounts=[400.0],
        product_name="Tabla de picada",
        candidate_count=1,
    )
    assert v.auto is True
    assert v.requires_human_review is False


# ── AC8b: each falsifying case yields auto=False + a card (requires_human_review) ────

def test_multi_candidate_product_never_auto():
    v = wv.compute_verdict(
        operation_type="REGISTER_SALE", utterance="vendí una tabla por 400",
        grounded_amounts=[400.0], product_name="Tabla", candidate_count=2,
    )
    assert v.auto is False and v.requires_human_review is True
    assert any("ambiguous" in r for r in v.reasons)


def test_null_or_unspoken_price_never_auto():
    # The amount came from the stored price, not the operator's words -> not grounded.
    v = wv.compute_verdict(
        operation_type="REGISTER_SALE", utterance="vendí una tabla",
        grounded_amounts=[350.0], product_name="Tabla", candidate_count=1,
    )
    assert v.auto is False
    assert any("ungrounded" in r for r in v.reasons)


def test_bare_confirmation_turn_never_auto():
    v = wv.compute_verdict(
        operation_type="REGISTER_SALE", utterance="dale",
        grounded_amounts=[400.0], product_name="Tabla", candidate_count=1,
    )
    assert v.auto is False
    assert "bare-confirmation" in v.reasons


def test_fabricated_number_not_in_utterance_never_auto():
    # A hijacked model stages 999 though the operator said 400: provenance laundering caught.
    v = wv.compute_verdict(
        operation_type="REGISTER_SALE", utterance="vendí una tabla por 400",
        grounded_amounts=[999.0], product_name="Tabla", candidate_count=1,
    )
    assert v.auto is False
    assert any("ungrounded" in r for r in v.reasons)


def test_product_not_named_in_utterance_never_auto():
    v = wv.compute_verdict(
        operation_type="REGISTER_SALE", utterance="anotá 400",
        grounded_amounts=[400.0], product_name="Tabla de picada", candidate_count=1,
    )
    assert v.auto is False
    assert "product-not-in-utterance" in v.reasons


def test_irreversible_op_never_auto():
    v = wv.compute_verdict(
        operation_type="UPDATE_PRODUCT_PRICE", utterance="poné la tabla a 500",
        grounded_amounts=[500.0], product_name="Tabla", candidate_count=1, irreversible=True,
    )
    assert v.auto is False
    assert "irreversible-op" in v.reasons


def test_non_reversible_set_op_never_auto():
    v = wv.compute_verdict(
        operation_type="REGISTER_PRODUCT", utterance="creá la tabla a 400",
        grounded_amounts=[400.0], product_name="Tabla", candidate_count=1,
    )
    assert v.auto is False


def test_add_stock_grounded_quantity_auto_posts():
    v = wv.compute_verdict(
        operation_type="ADD_STOCK", utterance="agregá 10 unidades de tabla",
        grounded_amounts=[10], product_name="Tabla", candidate_count=1,
    )
    assert v.auto is True


def test_expense_grounded_amount_auto_posts_without_a_product():
    v = wv.compute_verdict(
        operation_type="REGISTER_EXPENSE", utterance="gasté 200 en café",
        grounded_amounts=[200.0], product_name=None, candidate_count=1,
    )
    assert v.auto is True
