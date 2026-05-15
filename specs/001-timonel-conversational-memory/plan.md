---
name: timonel-conversational-memory-plan
spec: ./spec.md
created: 2026-05-15
---

# Plan — Timonel conversational memory and crash bound-fix

> The how. spec.md is the what + why. This file is the architecture, sequencing, and risk surface.

## Architecture sketch

A four-component picture. Storage, store interface, graph wiring, and error envelope.

**Storage.** Per-tenant SQLite at `data/clients/<phone>/business.db`, new `chat_history` table with columns `(turn_no INTEGER PK, role TEXT, content TEXT, metadata_json TEXT, created_at INTEGER)`. The tenant DB file is the partition. No global table. A second implementation behind `MEMORY_BACKEND=postgres` exists for installations on Postgres (the production deployment); columns mirror the SQLite shape with an explicit `tenant_phone TEXT NOT NULL` and a composite index `(tenant_phone, created_at DESC)`.

**Store interface.** `agents/memory/store.py` exposes a `MemoryStore` Protocol with `read(phone, limit) -> list[Turn]`, `append(phone, role, content, metadata)`, and `clear(phone)`. Three implementations: `InMemoryStore` (today's deque, kept as the test default and the cold-start fallback), `SqliteMemoryStore` (default in production), `PostgresMemoryStore` (opt-in). Selection via `MEMORY_BACKEND` env var. Reads always go through `tenant_context(phone)`, never a class-level dict.

**Graph wiring.** A new `memory_loader` node sits before the decomposer. It calls `MemoryStore.read(phone, limit=CHAT_CONTEXT_MAX_TURNS*2)` and writes `state["memory"] = {recent_turns, last_intent, pending_entities}`. The decomposer reads `state["memory"]["last_intent"]` before its regex gate. The router prompt continues to receive the `Contexto de conversación reciente:` block (existing wiring stays). On graph exit, `final_answer` writes the assistant turn back to the store. Every other node is wrapped in `safe_node(name)` which catches exceptions and writes `state["error"] = {"class": ..., "node": ..., "msg": ..., "incident_id": ...}` instead of raising.

**Error envelope.** `chat_with_tenant` returns `{response: str, metadata: {error_code: Optional[str], incident_id: Optional[str], navigation: Optional[dict]}}`. The widget reads `metadata.error_code` and looks it up in an extended `ERROR_FALLBACK_COPY`. The widget no longer scans assistant text for navigation triggers; it reads `metadata.navigation`.

```
                          ┌──────────────────┐
  user message ──────────▶│  memory_loader   │ reads last 6 turns from MemoryStore
                          └────────┬─────────┘ writes state.memory
                                   ▼
                          ┌──────────────────┐
                          │   decomposer     │ reads state.memory.last_intent
                          │     (Timonel)    │ collapses AMBIGUOUS replies
                          └────────┬─────────┘
                                   ▼
                ┌──────────────────────────────────┐
                │ router → resolver → write/read   │ each wrapped in safe_node
                └──────────────────┬───────────────┘
                                   ▼
                          ┌──────────────────┐
                          │   final_answer   │ writes assistant turn to store
                          └────────┬─────────┘ returns {response, metadata}
                                   ▼
                          ┌──────────────────┐
                          │  chat_widget.js  │ renders metadata.error_code,
                          │                  │ acts on metadata.navigation
                          └──────────────────┘
```

## Sequencing

| #  | Milestone                                                    | Effort  | Proof artifact                                                                                                  |
|----|--------------------------------------------------------------|---------|-----------------------------------------------------------------------------------------------------------------|
| M1 | Crash bound-fix and honest error surface                     | 2 days  | Screenshot turn 3 returns named copy, no `llm_unavailable` for typos. `safe_node` shipped. Widget renders `error_code`. |
| M2 | Persistent MemoryStore (no behavior change to memory consult)| 2 days  | `MemoryStore` Protocol, `SqliteMemoryStore` default, `ChatService` deque deleted. Container restart preserves prior turns. |
| M3 | Memory consult inside Timonel + AMBIGUOUS collapse           | 2 days  | Screenshot turn 2 routes to `REGISTER_PRODUCT`. Memory pre-fetch under 200ms p95. WhatsApp shares the store.    |
| M4 | Privacy, retention, consent (Edut hard floor)                | 1.5 days| 30-day TTL purge runs nightly. `olvidá todo` purges within 60s. Spanish consent line shipped at onboarding.     |

M1 is shippable alone. M2 unblocks M3. M4 ships in parallel with M3 once M2 lands.

## Top risks

| #  | Risk                                                                  | Likelihood | Impact | Mitigation                                                                                                       |
|----|-----------------------------------------------------------------------|------------|--------|------------------------------------------------------------------------------------------------------------------|
| R1 | Cross-tenant leakage via shared cache key, missing WHERE clause, or shared embedding index. | M | H | All store reads and writes go through `tenant_context(phone)`. `tests/integration/test_memory_isolation.py` writes under tenant A, reads under tenant B, asserts empty. Test fails on a deliberately broken predicate. |
| R2 | Context-window bloat that doubles LLM cost and degrades router accuracy. | M | M | History block hard-capped at 1500 input tokens. Oldest turns dropped first. Metric `chat_history_inject_tokens` exposed. |
| R3 | Memory pre-fetch adds first-token latency the user can feel.          | M | M | 200ms timeout on `MemoryStore.read`. Degrade to empty memory silently. Metric `memory_read_ms` exposed.          |
| R4 | Class-attribute deque is already racing across uvicorn workers (not just lost on restart). | H | M | Persistence is the fix. The class-level dict is deleted in T-012. |
| R5 | The Baileys WhatsApp path may not flow through `ChatService.chat_with_tenant`, leaving WhatsApp without memory. | M | M | T-020 first verifies the Baileys path. If divergent, an addendum task wires Baileys through the same store before M3 closes. |

## Dependencies

- `Light-Brands/infrastructure#40` — Nomad consul-template fix for `WHATSAPP_URL`. Independent of this spec but pairs with it; the backend's `/health` cannot turn green without it.
- Postgres availability for the optional `PostgresMemoryStore`. Already deployed in production via `postgres.service.consul`. No new infra needed.
- A short Sentry tag schema decision: `error_class`, `node`, `intent`, `incident_id`. Owner: Dario. Unblocking condition: Dario approves the four tag names before T-006 ships, or accepts the names as-proposed.

## Cost-shaped considerations

- **Time.** Roughly 7-8 person-days end to end. M1 is the unblocking 2-day slice. M3 is the user-visible win.
- **Money.** No new infra. Token budget cap on the history block keeps Anthropic spend within the existing per-turn envelope.
- **Attention.** Dario must answer Q1 (storage backend default) and Q2 (defer episode store) before M2 closes; both are short questions. The screenshot transcript is the regression case; he should re-run it once after M3 ships to confirm the felt experience.

## Why this shape and not another

The losing alternative was an embeddings-based semantic recall over the full conversation history, written to a vector store, queried per turn. The panel weighed it and Kaze and QI Master both rejected it for v1: it adds latency, infra cost, and a calibration-drift surface that the team is not equipped to monitor today. A turn buffer with persistent storage is the smallest change that closes both bug surfaces from the screenshot and gives the system room to grow into episodes and lessons later. We can layer semantic recall on top once the buffer and the episode store have produced enough signal to know what to recall.

## Verification plan

- M1: Replay the screenshot's turn 3 input ("un prodcuo al inventario") in `tests/unit/test_chat_service_crash.py` and assert the response is not the generic catch copy and `error_code` is non-null. Re-run it after every commit.
- M2: After deploy, restart the `beans-assistant` Nomad alloc, send a turn under a known phone, then send a follow-up and assert the prior turn is in the contextualized prompt. Logged in `runbooks/restart-survival.md`.
- M3: Replay the screenshot's two-turn sequence ("¿qué productos están por agotarse?" → "agreguemos") and assert the router classifies turn 2 as `REGISTER_PRODUCT` or `ADD_STOCK`. Measure memory pre-fetch latency for 100 synthetic turns; p95 must be under 200ms.
- M4: Trigger `olvidá todo` from a known phone; query the per-tenant DB and assert zero rows in `chat_history` within 60 seconds. Confirm the consent screen renders for a fresh tenant in a smoke test.
