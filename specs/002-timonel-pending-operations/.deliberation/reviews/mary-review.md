# Mary — Analyst review: Timonel deferred-operation completion

## 1. What problem is this actually solving?

The stated problem is "Timonel loses the operation." The real problem is that Timonel has no concept of a paused operation at all. It treats every turn as cold classification. The price question is not Timonel waiting for an answer; it is Timonel ending a thought and forgetting it happened. So "32 usd" arrives as a brand-new utterance with no slot to land in.

This is a state-machine problem wearing a memory costume. The context packet already proves the context was passed (193 chars, included the sale and the price question). Storage is fine. What is missing is a pending operation that owns the next turn. The user is not having a conversation, they are filling one form across three messages, and the system does not know the form exists.

The deeper need: a tenant must be able to answer a clarifying question in plain language and have the original money-moving action complete, exactly once, against the right product and quantity.

## 2. What is the smallest first version that proves the idea?

One paused operation, one missing field: REGISTER_SALE paused on null unit_price. When the write agent pauses, persist a pending record `{op: REGISTER_SALE, product, quantity, missing: [unit_price]}` keyed to the phone. On the next turn, before the router runs cold, check for a pending op. If the turn supplies the one missing field, fill it, record the sale at that price, set the product's price, and clear the pending op. If the reply is anything else, drop the pending op and route normally.

That single path replays Dario's exact transcript end to end. It proves resume-and-complete without building a general detour engine.

## 3. What 3 risks would kill this if ignored?

- **Double-recording.** If completing the resumed sale does not also short-circuit the router, the same turn could record the sale twice. Idempotency key on the pending op id, written once, is non-negotiable.
- **Wrong-binding on a stale pending op.** A pending op with no expiry will hijack an unrelated later turn ("32 usd" meant for a different product an hour later). Pending ops need a short TTL and must clear on any non-answer.
- **Ambiguous reply guessed instead of re-asked.** "32" with no currency, or "stanleys" again, must re-ask, never assume. The hard constraint says guessing produces a wrong financial record. One bad guess in a tenant's books destroys trust in the whole assistant.

## 4. What does success look like at 90 days?

Dario's transcript completes in two user turns (sell, then price) with the 40-unit sale recorded correctly, zero re-statements. Across live tenants: zero double-recorded sales attributable to resume, and the "¿Qué querés hacer con X?" cold-restart after a clarifying question disappears from logs. A measurable drop in abandoned write operations (paused, never completed). The mechanism generalizes to at least one second paused case beyond sale-needs-price without a rewrite.

## 5. What atomic tasks does this break into?

1. Define a `PendingOperation` shape (op_type, entities, missing_fields, created_at, id). Acceptance: type compiles and serializes round-trip in a unit test.
2. Persist a pending op when write_agent pauses the sale on null price, via `_build_pending_entities` with missing_fields set. Acceptance: paused sale leaves a readable pending record keyed to phone.
3. Capture quantity at pause time (currently dropped). Acceptance: pending record carries quantity=40 for the transcript case.
4. Add a pre-router resume check: if a pending op exists, attempt to fill its missing field from the turn. Acceptance: "32 usd" fills unit_price deterministically, router cold-classification skipped.
5. Complete the resumed sale idempotently (record sale + set price), one write. Acceptance: replaying the same turn twice records one sale.
6. Clear pending op on completion. Acceptance: a third turn routes fresh, no ghost resume.
7. Re-ask on ambiguous fill; do not guess. Acceptance: bare "32" or repeated "stanleys" re-asks, no sale recorded.
8. Drop pending op on cancel or topic change. Acceptance: "dejá, mejor agregá stock" clears the pending sale.
9. TTL expiry on pending ops. Acceptance: a pending op older than the window is ignored and cleared.
10. ARCHITECTURE.md D-007: pending-operation state machine and per-field ownership. Acceptance: doc renders, D-007 present.
11. End-to-end test of Dario's transcript. Acceptance: two user turns, one correct 40-unit sale.

## 6. The one thing only analysis would have noticed

The router's two failure turns are not the same failure. Turn "32 usd" → "Me falta un dato: el producto" is a re-extraction miss: the product was knowable from context and the LLM dropped it. Turn "stanleys" → "¿Qué querés hacer?" is a total intent loss: even the operation is gone. A pure re-extraction fix would patch the first and leave the second, because the second proves there is no operation to extract into. That is the tell that this is state-machine work, not prompt-tuning. Spend the effort on the pending-operation store; do not let it become a router prompt patch that fixes one transcript and reopens the bug on the next shape.
