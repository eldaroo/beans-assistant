# Bob (Scrum Master) — Timonel pending-operation completion

## 1. What problem is this actually solving?

A paused write operation gets lost. Timonel asks for a missing field, the user supplies it, and the original operation is gone. The fix is a deterministic pending-operation store that resumes and completes the original write, so the user never re-states what they already said.

## 2. Smallest first version that proves the idea

Persist exactly one pending REGISTER_SALE when the write pauses for a NULL price. On the next turn, if the reply parses as a price, set the price and complete the held sale idempotently. One operation type, one missing field, one happy path. That alone makes Dario's transcript work end to end.

## 3. Three risks that would kill this

- Double-recording a sale. Completion must be idempotent, keyed so a retry never books twice.
- The router re-classifying the price turn cold and stomping the held state. The pending store must take precedence over a fresh classification when a held operation matches.
- Stale held state binding to the wrong later turn. A held op needs a TTL and an explicit clear on cancel, topic change, or completion.

## 4. Success at 90 days

Zero double-booked sales in tenant ledgers. Paused-then-resumed sales complete on the supplying turn with no re-statement. The pattern generalizes to at least one more paused operation (ADD_STOCK) without a rewrite. Carry-over of "lost operation" bug reports drops to zero.

## 5. Atomic tasks (dependency-ordered, milestone cohorts)

### M1 — makes Dario's exact transcript work end to end (SHIPPABLE ALONE)

1. Define `PendingOperation` typed record (op_type, product, quantity, missing_fields, ttl, idempotency_key) in `backend/services/chat_service.py`. AC: type exists, unit test constructs it. 2h. autodev
2. Capture quantity + missing on the sale-needs-price pause in `agents/write_agent.py`. AC: `_build_pending_entities` returns `missing_fields=["unit_price"]` and `quantity=40` for the pause case (test). 3h. autodev
3. Persist one pending op on pause via `_append_history` lean metadata. AC: after pause turn, stored metadata carries `pending_operation` (test). 3h. autodev
4. Detect a resume turn: pending op present + reply parses as price. AC: unit test, "32 usd" against a held sale returns resume=true. 4h. autodev
5. Resume path short-circuits the router so it cannot re-classify cold. AC: graph test, held-op turn skips fresh classification. 5h. autodev
6. Fill price then complete the original sale in one resume. AC: integration test records a 40-unit sale at 32. 6h. autodev
7. Idempotency key on completion. AC: replaying the resume turn books the sale once (test). 5h. autodev
8. Clear pending op on completion. AC: post-resume metadata has no `pending_operation` (test). 2h. autodev
9. End-to-end transcript test of Dario's four turns. AC: test reproduces the verbatim flow and books one 40-unit sale at 32. 4h. autodev
10. ARCHITECTURE.md D-007 records the pending-operation state machine. AC: D-007 present at repo root. 1h. human

### M2 — generalize and harden

11. TTL expiry on held ops. AC: expired op ignored, falls through to fresh classification (test). 4h. autodev
12. Cancel / topic-change clears pending op. AC: "no, dejá" mid-detour clears state (test). 4h. autodev
13. Ambiguous reply re-asks, never guesses. AC: non-price reply re-asks for price (test). 4h. autodev
14. Generalize the machine to ADD_STOCK paused-on-missing-field. AC: paused stock add resumes (test). 6h. autodev
15. Live prod verification on Nomad of the transcript. AC: Dario confirms in Bitacora AI. 2h. human

## 6. The one thing only I would have noticed

Tasks 4 and 6 are two stories, not one. Extraction (does this turn supply the field) and completion (resume the held write) fail for different reasons and must be independently testable. Fusing them hides which half broke when the ledger is wrong.

---

**Summary:** M1 (tasks 1-10) is the cohort that makes Dario's transcript work end to end, and M1 is the single milestone shippable alone.
