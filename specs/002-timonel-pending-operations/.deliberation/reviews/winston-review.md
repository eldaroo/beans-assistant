# Winston review: Timonel deferred-operation completion

## 1. What problem is this actually solving

A paused write operation is reconstructed next turn by an LLM that does not reliably re-extract it. Product, quantity, and operation type live only as prose in the history buffer, so the router re-classifies cold and loses them. Stop reconstructing: capture the paused operation as structured state, resume it deterministically when the field arrives.

## 2. Smallest first version that proves the idea

One operation, one field: REGISTER_SALE paused on a NULL-price product. When `write_agent` blocks the sale, write a `PendingOperation` keyed to the phone carrying `op=REGISTER_SALE`, resolved `product_id`, `quantity`, `missing=[unit_price]`. Next turn, before the router runs, a deterministic gate checks for a pending record and a numeric reply. If both hold, fill `unit_price`, rebuild the original entities, route straight to resolver/write. The 40-at-32 sale commits without the router being asked. Everything else falls through to today's path.

## 3. Three risks that would kill this

1. **Double-recording a sale.** A retried turn resumes the same record twice. Without an idempotency token on completion, the books gain a phantom sale. This is the constraint, not an edge case.
2. **Resuming the wrong thing.** The reply looks like a price but the user changed their mind ("no, mejor cancelá"). A gate that fires on any number after a pending sale guesses. It must yield to cancel and ambiguity, re-asking rather than binding.
3. **Stale record.** The store is in-process. A restart, or a reply 40 minutes later, must not resume a phantom. Expiry is correctness, not hygiene.

## 4. Success at 90 days

Dario's transcript completes in two turns: pause for price, supply price, sale recorded. Zero double-recorded sales attributable to resume. Resume covers sale-needs-price plus product-needs-name, and runs with no router LLM call, measurable in logs.

## 5. Atomic tasks (each with a one-line acceptance)

- **T1** `PendingOperation` TypedDict + `agents/pending.py` builder. _Acceptance: a record builds from a blocked-sale state and round-trips._
- **T2** `write_agent` sale-price block emits a pending record (op, product_id, quantity, missing). _Acceptance: blocking a NULL-price sale returns `pending_operation` in the delta._
- **T3** Persist the record in `ChatService` keyed by phone, TTL + one-writer clearing. _Acceptance: record survives one turn, gone after TTL._
- **T4** Deterministic `resume_gate` before the router that fills the field and rebuilds entities on a match. _Acceptance: "32 usd" after a paused 40-unit sale routes to resolver with no router call._
- **T5** Idempotency: stamp each record with `op_token`; completion records it and refuses a second commit. _Acceptance: replaying the resume turn commits one sale, not two._
- **T6** Cancel transition: a cancel or non-matching reply clears the record and falls through. _Acceptance: "cancelá" after a pause clears pending, records nothing._
- **T7** Ambiguous reply re-asks. _Acceptance: a non-numeric, non-cancel reply re-asks and keeps the record._
- **T8** Extend to product-needs-name behind the same gate. _Acceptance: a paused REGISTER_PRODUCT resumes on a name reply._
- **T9** Goldens for the transcript + the three risks. _Acceptance: eval green; the double-record case asserts exactly one sale row._

## 6. The one thing only architecture would notice

The resume gate must run **before** the router and own the bypass decision, because the moment a router LLM call sits on the resume path the determinism constraint is already lost. The existing `pending_entities` seam is a context hint fed back into the router prompt: the wrong layer, because it makes the LLM the resume mechanism. The pending record is not a prompt enrichment, it is a state machine the code drives, and the router never sees the resume turn.
