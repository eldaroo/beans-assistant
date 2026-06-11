# Bob review — Timonel conversational memory + crash

## 1. What problem is this actually solving

Two problems that share one symptom. First, Timonel and the router cannot see prior turns, so a user who said "productos por agotarse" then "agreguemos" gets a disambiguation question and a side-effect at the same time. Second, any single-turn exception bubbles up as the JS catch copy "No pude procesar tu mensaje ahora", which masked a real backend error on the turn 3 typo. Memory is the feature. Crash is a bound-fix that ships beside it.

## 2. Smallest first version that proves the idea

Keep the existing in-process deque API. Move the storage behind a `MemoryStore` interface with two implementations: the current deque (default) and a SQLite-backed table at `data/clients/<phone>/memory.db`. Wire `chat_service` to the store. Add a single `last_user_intent` and `last_named_entities` snapshot the decomposer reads before its regex gate. That is enough to collapse "agreguemos" against the prior "productos" turn. No embeddings, no episodic search, no cross-channel sync yet. Memory survives one container restart on the same phone. That single behavior is the proof.

## 3. Three risks that would kill this if ignored

- **Tenant boundary leak.** Memory keyed only by phone, written to a shared SQLite without tenant context, will cross-contaminate when two tenants share a number prefix or when the WhatsApp connector reuses a sender. Persistence must inherit `tenant_context`.
- **Decomposer regression.** The regex gate today is pure and free. Adding a memory lookup before it turns every turn into an I/O call. If the store is slow or unavailable, the decomposer must degrade to today's behavior, not block.
- **Wrong root cause on the crash.** Shipping memory while assuming the crash is an LLM timeout means the next typo trips the same wire. The fix has to land server-side error surfacing (structured `error` field in the response) before the JS catch copy is treated as the user-visible truth.

## 4. Success at 90 days

Conversation context survives a Nomad restart on web and WhatsApp. Sub-second p95 on memory read. Zero cross-tenant leaks in audit. The "agreguemos after productos" path resolves to ADD_STOCK or REGISTER_PRODUCT without re-asking. Crash copy "No pude procesar..." appears in less than 0.5% of turns and every occurrence has a logged structured cause.

## 5. Atomic tasks

| ID | Title | Acceptance | Owner |
|----|-------|------------|-------|
| M1-T1 | Reproduce turn 3 crash in `tests/unit/test_chat_service_crash.py` | Test sends "un prodcuo al inventario" with prior history and asserts the response is not the generic catch copy | autodev |
| M1-T2 | Surface backend exception as `metadata.error` in `chat_with_tenant` | When `_invoke_graph` raises, return `(fallback_text, {"error": "internal_exception", "trace_id": ...})` instead of raising into JS catch | autodev |
| M1-T3 | JS error map: render `metadata.error` codes distinctly | `chat_widget.js` `ERROR_FALLBACK_COPY` gets `internal_exception` entry; catch handler uses it before the generic copy | autodev |
| M1-T4 | Structured logging for every resolver/write_agent exception | Each exception in graph nodes writes one JSON log line with `phone`, `intent`, `node`, `error_class` | autodev |
| M2-T1 | Define `MemoryStore` Protocol in `agents/memory/store.py` | Protocol exposes `read(phone, limit) -> list[Turn]`, `append(phone, turn)`, `clear(phone)`. Type-check passes | autodev |
| M2-T2 | Refactor `ChatService._history_by_key` to use `MemoryStore` | All existing tests pass with `InMemoryStore` as default | autodev |
| M2-T3 | Add `SqliteMemoryStore` backed by `data/clients/<phone>/memory.db` | Round-trip test writes 6 turns, reads 6, survives connection close | autodev |
| M2-T4 | Wire store selection via `MEMORY_BACKEND` env var | `MEMORY_BACKEND=sqlite` flips the default; deque remains fallback | autodev |
| M2-T5 | Tenant-context guard on store writes | Test asserts a write under tenant A cannot be read under tenant B even on phone collision | autodev |
| M3-T1 | Decomposer reads `last_named_entities` from store before regex gate | Test: prior turn returns "productos vacios"; current turn "agreguemos" routes to ADD_STOCK / REGISTER_PRODUCT, not Gastos | autodev |
| M3-T2 | Bound timeout on memory read (50ms) with degrade-to-today fallback | Test injects a slow store and asserts decomposer still returns within budget | autodev |
| M3-T3 | Persist memory on WhatsApp dispatcher path | Send two messages via Baileys path in a test; second turn sees first in history | autodev |
| M3-T4 | Restart-survival smoke test | Manual runbook: send turn, restart Nomad alloc, send follow-up, verify context is read back | human |
| M3-T5 | Audit script for cross-tenant leaks | `scripts/audit_memory_isolation.py` scans all tenant memory dbs and asserts no foreign-tenant turns | autodev |

Milestones: **M1 (crash fix)** can ship alone. **M2 (storage refactor)** ships next, no behavior change. **M3 (memory consult)** is the user-visible feature. M1 and M2 unblock M3 but M3 only requires M2.

## 6. The one thing only my faculty would have noticed

Both bug surfaces in Dario's screenshot are off-by-one feedback failures: turn 2 fired an action while still asking the question (no commit gate between disambiguation and side-effect), and turn 3 fired the JS catch copy while the server still held the real error (no commit gate between transport failure and presentation). Memory is the right feature, but the spec needs an explicit rule: **no user-visible side-effect or fallback copy fires until the prior step has produced a final, structured outcome**. That is a Definition of Done for every graph edge, not a memory feature. Add it as a non-negotiable acceptance line on M1-T2 and M3-T1, otherwise this same shape resurfaces under a different intent next sprint.
