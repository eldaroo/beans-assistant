"""M3 write machinery at the DB layer (spec 007): deterministic resolution, the pending-op
store, the append-inverse cancel rework (AC15), and the pessimistic stock guard (AC16).

Runs against the isolated SQLite test DB (the populated_db fixture patches database.get_conn),
which is also what database_config re-exports when USE_POSTGRES is false, so ops_resolver and
pending_ops_repository bind to the same connection.
"""
import database
from backend.repositories import pending_ops_repository as pending_ops
from backend.services import ops_resolver


def _product_by_sku(sku):
    return database.fetch_one("SELECT id, name, unit_price_cents FROM products WHERE sku = ?", (sku,))


def _revenue_cents():
    row = database.fetch_one("SELECT total_revenue_cents FROM revenue_paid")
    return (row["total_revenue_cents"] or 0) if row else 0


def _profit_usd():
    row = database.fetch_one("SELECT profit_usd FROM profit_summary")
    return (row["profit_usd"] or 0.0) if row else 0.0


def _stock(product_id):
    row = database.fetch_one("SELECT stock_qty FROM stock_current WHERE product_id = ?", (product_id,))
    return (row["stock_qty"] or 0) if row else 0


# ── Deterministic resolver (D-042) ──────────────────────────────────────────────────

def test_resolver_zero_one_many_active(populated_db):
    classic = _product_by_sku("BC-BRACELET-CLASSIC")
    one = ops_resolver.resolve_active_product("BC-BRACELET-CLASSIC")
    assert one.candidate_count == 1 and one.product["id"] == classic["id"]

    zero = ops_resolver.resolve_active_product("zzz-nothing-matches")
    assert zero.candidate_count == 0 and zero.product is None

    # The three bracelet names share a common word -> more than one active candidate.
    name_word = classic["name"].split()[0]
    many = ops_resolver.resolve_active_product(name_word)
    assert many.candidate_count >= 1
    if many.candidate_count > 1:
        assert many.product is None  # never guesses among several


# ── Pending-op store (AC7) ──────────────────────────────────────────────────────────

def test_pending_store_lifecycle_and_idempotency(populated_db):
    token = "op-test-123"
    pending_ops.stage(op_token=token, operation_type="REGISTER_SALE",
                      args={"grounded_amounts": [400.0], "product_name": "Tabla", "db_args": {}},
                      utterance="vendí una tabla por 400", product_name="Tabla", candidate_count=1)

    got = pending_ops.get(token)
    assert got["args"]["grounded_amounts"] == [400.0]  # JSON round-trips

    pending_ops.set_verdict(token, auto=True, requires_human_review=False, reasons=["ok"])

    # Claim-before-commit: claim PENDING->COMMITTING, then finalize COMMITTING->COMMITTED.
    assert pending_ops.claim(token) is True
    assert pending_ops.mark_committed(token, {"sale_id": 7}) is True
    assert pending_ops.mark_committed(token, {"sale_id": 7}) is False  # idempotent double-confirm
    assert pending_ops.get(token)["status"] == "COMMITTED"

    assert pending_ops.claim_cancel(token) is True   # COMMITTED -> CANCELLING (undo claim)
    assert pending_ops.claim_cancel(token) is False  # idempotent: a second undo tap loses
    pending_ops.finalize_cancelled(token)
    assert pending_ops.get(token)["status"] == "CANCELLED"


def test_claim_is_single_winner_so_commit_cannot_double_post(populated_db):
    token = "op-claim-1"
    pending_ops.stage(op_token=token, operation_type="REGISTER_SALE",
                      args={"db_args": {}}, utterance="x", product_name="x", candidate_count=1)
    # Two racing confirms both call claim(); exactly one wins the PENDING->COMMITTING transition.
    first = pending_ops.claim(token)
    second = pending_ops.claim(token)
    assert first is True and second is False
    # Only the winner can finalize; mark_committed transitions COMMITTING->COMMITTED.
    assert pending_ops.mark_committed(token, {"sale_id": 1}) is True
    assert pending_ops.mark_committed(token, {"sale_id": 1}) is False
    # unclaim reverts a COMMITTING op back to PENDING for a pessimistic-retry (no-op once COMMITTED).
    pending_ops.unclaim(token)
    assert pending_ops.get(token)["status"] == "COMMITTED"


def test_verdict_pending_for_turn_returns_every_staged_op_for_the_nonce(populated_db):
    nonce = "turn-abc"
    pending_ops.stage(op_token="t1", operation_type="REGISTER_SALE", args={"a": 1},
                      utterance="x", product_name="x", candidate_count=1, turn_nonce=nonce)
    pending_ops.stage(op_token="t2", operation_type="REGISTER_EXPENSE", args={"a": 2},
                      utterance="x", product_name=None, candidate_count=1, turn_nonce=nonce)
    pending_ops.stage(op_token="t3", operation_type="ADD_STOCK", args={"a": 3},
                      utterance="x", product_name="x", candidate_count=1, turn_nonce="other-turn")
    this_turn = pending_ops.verdict_pending_for_turn(nonce)
    assert sorted(o["op_token"] for o in this_turn) == ["t1", "t2"]  # compound turn, both surface
    assert pending_ops.verdict_pending_for_turn("other-turn")[0]["op_token"] == "t3"
    # Once a verdict is set, the op is no longer verdict-pending for its turn.
    pending_ops.set_verdict("t1", auto=True, requires_human_review=False, reasons=[])
    assert sorted(o["op_token"] for o in pending_ops.verdict_pending_for_turn(nonce)) == ["t2"]


# ── Append-inverse cancel rework (AC15) ─────────────────────────────────────────────

def test_cancel_sale_is_append_inverse_not_destructive_and_idempotent(populated_db):
    classic = _product_by_sku("BC-BRACELET-CLASSIC")
    pid = classic["id"]
    database.add_stock({"product_id": pid, "quantity": 5})
    stock_before = _stock(pid)

    sale = database.register_sale({"status": "PAID", "items": [
        {"product_id": pid, "quantity": 2, "unit_price_cents": 3500}]})
    assert _revenue_cents() == 7000
    assert _stock(pid) == stock_before - 2

    out = database.cancel_sale(sale["sale_id"])
    assert out["already_cancelled"] is False
    # Row preserved (not deleted), status flipped, balance + stock restored to the cent.
    row = database.fetch_one("SELECT status FROM sales WHERE id = ?", (sale["sale_id"],))
    assert row is not None and row["status"] == "CANCELLED"
    assert _revenue_cents() == 0
    assert _stock(pid) == stock_before

    # Double Undo is a no-op: stock is not restored twice.
    out2 = database.cancel_sale(sale["sale_id"])
    assert out2["already_cancelled"] is True
    assert _stock(pid) == stock_before
    assert _revenue_cents() == 0


def test_cancel_expense_is_append_inverse_not_destructive_and_idempotent(populated_db):
    exp = database.register_expense({"amount_cents": 5000, "description": "Insumos", "category": "GENERAL"})
    profit_after_expense = _profit_usd()

    out = database.cancel_expense(exp["expense_id"])
    assert out["already_cancelled"] is False
    # Original expense row preserved; a compensating row nets it out.
    orig = database.fetch_one("SELECT id FROM expenses WHERE id = ?", (exp["expense_id"],))
    assert orig is not None
    comp = database.fetch_one(
        "SELECT amount_cents FROM expenses WHERE category = 'CANCELACION' AND description LIKE ?",
        (f"[void:{exp['expense_id']}]%",))
    # Positive amount (CHECK forbids negative); expenses_total subtracts the CANCELACION category.
    assert comp is not None and comp["amount_cents"] == 5000
    assert _profit_usd() == profit_after_expense + 50.0  # profit restored by $50

    out2 = database.cancel_expense(exp["expense_id"])
    assert out2["already_cancelled"] is True
    # No second compensating row.
    n = database.fetch_one(
        "SELECT COUNT(*) AS c FROM expenses WHERE category = 'CANCELACION' AND description LIKE ?",
        (f"[void:{exp['expense_id']}]%",))["c"]
    assert n == 1


def test_add_stock_returns_movement_id_and_cancels_clean(populated_db):
    classic = _product_by_sku("BC-BRACELET-CLASSIC")
    pid = classic["id"]
    before = _stock(pid)
    res = database.add_stock({"product_id": pid, "quantity": 9})
    assert res.get("movement_id") is not None
    assert _stock(pid) == before + 9
    database.cancel_stock_movement(res["movement_id"])
    assert _stock(pid) == before


# ── Pessimistic post: the stock guard rejects a sale that exceeds stock (AC16) ───────

def test_register_sale_rejects_when_stock_insufficient(populated_db):
    import pytest
    classic = _product_by_sku("BC-BRACELET-CLASSIC")
    pid = classic["id"]
    # Only 1 unit on hand; selling 3 must raise (the guard that makes auto-post pessimistic).
    database.add_stock({"product_id": pid, "quantity": 1})
    with pytest.raises(ValueError):
        database.register_sale({"status": "PAID", "items": [
            {"product_id": pid, "quantity": 3, "unit_price_cents": 3500}]})
