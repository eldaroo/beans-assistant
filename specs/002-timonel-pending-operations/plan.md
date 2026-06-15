# Plan: Timonel deferred-operation completion

> How the spec at `./spec.md` gets built. Architecture decisions live in `../../ARCHITECTURE.md` (D-007 through D-012).

## Architecture sketch

A paused write becomes a structured record, not prose in the history buffer. The flow:

```
turn N   (pause):   decomposer -> router -> resolver -> write_agent
                    write_agent sees product.unit_price_cents IS NULL
                    -> emits PendingOperation{op, product_id, quantity, missing=[unit_price], op_token, created_at}
                    -> ChatService stores it per phone (single active, TTL)
                    -> replies "Necesito el precio de venta de X..."

turn N+1 (field):   resume_gate (NEW, runs before decomposer/router)
                    - cancel parse first: "no, deja" -> clear, write nothing
                    - else typed-field match: "32 usd" validates as price?
                        no  -> clear-or-keep, re-ask, no router cold-classify needed
                        yes -> fill unit_price, rebuild REGISTER_SALE entities in code
                            -> emit CONFIRMATION "registro 40 Termos Stanley a 32, total 1280, dale?"
                            -> write NOTHING; pending op now awaits-confirm
                    (no pending op present -> fall through to today's decomposer/router path unchanged)

turn N+2 (confirm): resume_gate sees awaits-confirm pending op
                    - affirmative -> clear op_token, commit ONE sale (idempotent), audit line, truthful copy
                    - negative    -> clear, write nothing
```

Module table:

| Module                      | Responsibility                                                        |
|-----------------------------|-----------------------------------------------------------------------|
| `agents/pending.py` (new)   | `PendingOperation` type + pure helpers: build, match-field, validate, parse-cancel, parse-affirmative. No DB, no LLM. |
| `agents/write_agent.py`     | Emit the `PendingOperation` delta on the NULL-price sale block.        |
| `backend/services/chat_service.py` | Persist/expire one pending op per phone alongside `_history_by_key`; run the resume decision before `_invoke_graph` or as the new entry node. |
| `resume_gate` (new node)    | Cancel parse, field match, entity rebuild, confirmation emit, commit-on-affirmative, idempotency, audit. |
| `graph.py`                  | Wire `resume_gate` as the entry node ahead of the decomposer.         |
| `agents/router.py`          | Unchanged. Never classifies a resume turn.                            |

The pending op lives in-process (D-008), keyed by phone via `_history_key`, expired by a dedicated `pending_ttl_seconds` (default 3 min, Q3). It dies on restart by design: a half-finished sale resumed after a deploy is the hazard we reject.

## Sequencing

| Milestone | Theme | Tasks | Surfaces | Shippable alone |
|-----------|-------|-------|----------|-----------------|
| M1 | Safe deferred completion of the sale-needs-price path, end to end | T-001 .. T-010 | S1 S2 S3 S4 S5 S6 S7 | Yes. Makes Dario's transcript work and is safe on its own because the confirmation gate, cancel, TTL, and idempotency all land here. Nothing auto-writes without confirmation. |
| M2 | Generalize and verify | T-011 .. T-012 | S8 S9 | No. Extends a proven M1 to a second paused op and verifies live. |

M1 is the moral floor: per Edut and Mar'ah, no auto-completed sale may ship without the confirmation gate (T-005, T-006), the cancel path (T-009 via T-004), the TTL (T-007), and idempotency (T-007). These are not hardening deferred to M2; they are the cost of the first safe write.

## Risks

| Risk | Mitigation |
|------|------------|
| A wrong guess records a real sale in a tenant's books (Edut, Mar'ah A3). | Confirmation gate before any write (AC4, AC5). The field-supplying turn never writes. |
| Double-recording on a retried or double-sent turn (Mar'ah A4). | `op_token` cleared before commit, recorded with the sale, duplicate token is a no-op (AC6, D-010). |
| A stale or post-detour bare number resurrects the wrong pending op (Mar'ah A5, A1). | TTL expiry (AC7) plus the rule that only a validated field on a still-fresh op resumes, and a non-price turn does not consume the op (AC8). |
| Correctness placed behind the Gemini router again. | Resume is deterministic code ahead of the router (D-007). The router never sees a resume turn (AC3). |
| The new entry node breaks the existing decomposer sub-input loop or the single-intent fast path. | `resume_gate` fails open (D-011 convention): no pending op or any internal failure falls through to today's path unchanged. Graph tests assert the non-resume path is untouched. |

## Dependencies

- No new external services. No new Python packages expected (price parsing reuses existing extraction helpers).
- Complementary to spec #63 (durability). This spec does not block on it and does not require it. When #63 lands, the pending record rides the same in-process-to-durable migration (D-008 implication).
- The live verification task (T-012) depends on the standard Nomad deploy path used on 2026-06-14 (CI build, then patch the `beans-assistant` job to the new image, single-worker uvicorn).

## Cost-shaped considerations

M1 is roughly 35 to 45 hours of build across 10 tasks, drained as one `/develop --headless` cohort. The cost is concentrated in the resume_gate node and the regression suite, which is correct: the suite is the proof the guards hold, and on a money app the proof is the deliverable.
