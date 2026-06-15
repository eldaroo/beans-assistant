# Amelia review — Timonel deferred-operation completion

## 1. The problem

A write that pauses for a missing field forgets the whole operation. The pause is born at `write_agent.py:326-342`: the NULL-price sale block returns `error`/`final_answer` but never sets `missing_fields` and never lifts `quantity`/`product_id` into a persisted shape. So `chat_service._build_pending_entities` (`chat_service.py:142`, `if not missing_fields: return None`) emits `None`, `_append_history` stores nothing, and the resuming turn classifies cold. Even when the price is caught, the router lands `UPDATE_PRODUCT_PRICE` (`write_agent.py:475-496`) which sets the price and stops. The 40-unit sale is never recorded.

## 2. Smallest first version

Do the resume deterministically in `chat_service`, before the graph runs, scoped to exactly one case: a bare-price reply to a pending sale.

Write the pending record on the pausing turn at the NULL-price block (`write_agent.py:331-342`): add `pending_operation` to the returned delta carrying `op="REGISTER_SALE"`, `product_id`, `quantity`, `unit_price_cents=None`. `chat_with_tenant` (`chat_service.py:427-442`) already reads `result.get(...)` and persists into history metadata; add a `pending_operation` key alongside `pending_entities` in `_append_history` (`chat_service.py:212-214`).

Read it on the resuming turn at the top of `_invoke_graph` (`chat_service.py:239`), right after `_build_message_with_context`. If `last_metadata.pending_operation.op == "REGISTER_SALE"` and the raw `message` parses to a bare price (one money token, regex), synthesize the completed `register_sale` call with the stored `product_id`/`quantity` and inline `unit_price_cents`, skip `graph.invoke`, and return a result envelope shaped like a committed write. The graph never sees the price turn. Anything not a bare price falls through to the graph untouched.

This is right in `chat_service`, not `write_agent`: the write_agent only sees one turn's state and has no history; the cross-turn join lives where history lives.

## 3. Three killer risks

- Double-record. If the synth path and a router-driven `UPDATE_PRODUCT_PRICE` both fire, the books get two writes. Mitigation: clear `pending_operation` from history the instant the synth commits, and gate synth on an idempotency key (phone + product_id + quantity + turn count).
- Wrong bind. `register_sale` here uses the inline `unit_price_cents` override (`write_agent.py:316`), so it must NOT also call `update_product_price`. The catalog price must stay NULL unless the user asked to set it. Binding `quantity` to the wrong product is the financial-error case: store `product_id`, never re-resolve by name.
- The detour. User replies "no, dejá" or "mejor 50 unidades", not a price. The bare-price regex must reject anything ambiguous and fall through to the graph; never guess a number out of a sentence.

## 4. Success at 90 days

The verbatim transcript completes in two turns: "vendí 40 stanleys" then "32 usd" records a 40-unit sale at 32. Zero double-records in prod logs. The pending record generalizes to one more safe case (expense-needs-amount) behind the same store, with sale-needs-price proven first.

## 5. Atomic tasks

1. Add `pending_operation` to the NULL-price return delta in `write_agent.py` (~line 331). Accept: delta dict contains `pending_operation` with op/product_id/quantity.
2. Persist `pending_operation` in `_append_history` (`chat_service.py:212`). Accept: history metadata round-trips the field.
3. Add `_parse_bare_price(message) -> int|None` in `chat_service.py`. Accept: "32 usd" -> 3200; "no dejá" -> None.
4. Add `_try_resume_pending(phone, message)` reading last `pending_operation` (`chat_service.py`, before `_invoke_graph` body). Accept: returns synthesized result only for sale+bare-price.
5. Wire the resume check into `_invoke_graph` (`chat_service.py:239`); skip `graph.invoke` on hit. Accept: graph not called on the price turn.
6. Clear `pending_operation` on synth commit (`chat_service.py:_append_history`). Accept: next bare price does not re-fire.
7. Idempotency guard in `_try_resume_pending`. Accept: replaying the same price turn writes one sale.
8. Unit test the four-turn transcript end to end. Accept: one sale row, qty 40, price 3200, catalog price stays NULL.

## 6. What only a dev would notice

`_build_message_with_context` already injects a `pending_marker` (`chat_service.py:114`) telling the router a price is coming, but that marker rides on `pending_entities`, which the sale block never populates because it never sets `missing_fields`. The hint plumbing is built and wired to a producer that is silent. Fix the producer, not the router prompt.
