# Winston review — Timonel conversational memory

## 1. What problem is this actually solving?

Two problems collapsed into one symptom. First, conversational state is volatile: the deque in `ChatService` lives in the FastAPI process heap, so any Nomad alloc restart wipes every tenant's history simultaneously. Second, the graph has no fault-isolation boundary at node level, so a downstream throw renders as the dispatcher fallback copy `No pude procesar tu mensaje ahora`, which is indistinguishable from a typo or a real model outage. The user cannot tell which one happened, and neither can we from the log line. Memory durability and per-node fault containment are the same architectural gap viewed from two angles: the graph treats every turn as cold and every exception as terminal.

## 2. What is the smallest first version that proves the idea?

Move the deque into Postgres, behind the same `_history_by_key` interface, with one table `chat_history(tenant_phone, turn_seq, role, content, metadata jsonb, created_at)` partitioned by tenant_phone and pruned by TTL. Keep `CHAT_CONTEXT_MAX_TURNS` and `CHAT_CONTEXT_TTL_SECONDS` as the read window. Wrap each LangGraph node in a try-or-degrade adapter that, on exception, sets `state.error` and routes to `final_answer` with a node-specific message instead of the generic copy. Both surfaces (web widget and Baileys) already converge on `ChatService.chat_with_tenant`, so durability fixes both at once. No Redis, no embeddings, no cross-channel coordination yet. Ship the persistence and the fault boundary; defer everything else.

## 3. What 3 risks would kill this if ignored?

- **Multi-tenant leakage.** The history table must enforce `tenant_phone` as a write-time and read-time predicate, with a unique index that includes it. One missing WHERE clause and a tenant sees another tenant's conversation. Treat this like the per-tenant SQLite boundary: row-level enforcement, not application-trust.
- **Hot-path Postgres write per turn.** Every user message currently rewrites the deque in memory; moving to Postgres adds two writes per turn (user + assistant). At low scale this is invisible. The risk is the absence of a connection-pool ceiling and no async write path; the chat surface stalls if the pool saturates.
- **Context bloat poisoning the router.** The router prompt already pre-pends `Contexto de conversación reciente`. If memory grows beyond the current 6-turn window, the prompt size inflates and the AMBIGUOUS classification rate climbs because the model loses the most-recent signal. Cap it.

## 4. What does success look like at 90 days?

Container restarts no longer reset conversation. P95 turn latency stays within 200 ms of the current baseline. Zero tenant-leakage incidents in the audit log. The graph never returns the generic dispatcher fallback for a typo'd input again; failures route to a node-attributed message that names which step degraded. The `pending_entities` and `last_intent` markers survive across restarts. WhatsApp and web see the same history because both flow through `ChatService.chat_with_tenant`.

## 5. Atomic tasks

1. **Schema chat_history table.** Migration creates table with composite index on (tenant_phone, turn_seq desc); accepted when alembic up/down runs clean against current Postgres.
2. **Postgres-backed history store.** New `ChatHistoryRepo` class with `read(phone, limit)` and `append(phone, role, content, metadata)`; accepted when unit tests pass against a Postgres testcontainer.
3. **Swap deque for repo in ChatService.** Keep the same method shapes so callers do not change; accepted when existing chat_service tests pass unchanged.
4. **TTL pruner job.** Background task or cron deletes rows older than `CHAT_CONTEXT_TTL_SECONDS`; accepted when a 31-minute-old row is gone on next read.
5. **Per-node fault boundary.** Wrap router, resolver, write_agent, read_agent in a decorator that catches, logs with node name, and writes a node-attributed `state.error`; accepted when an injected exception in resolver yields `Tuve un problema resolviendo tu producto, probá de nuevo` not the generic copy.
6. **Decomposer reads history.** Pass last assistant turn into `should_decompose` so a typo'd reply to a clarifier is not re-decomposed; accepted when the screenshot scenario (turn 3 typo after a clarifier) routes back to AMBIGUOUS, not to the generic fallback.
7. **Multi-tenant boundary test.** Integration test writes for tenant A, reads for tenant B, asserts empty; accepted when test fails on a deliberately broken WHERE clause.
8. **Context window cap.** Hard limit total context bytes injected into the router prompt; accepted when a synthetic 100-turn history truncates to the configured byte budget.
9. **Metrics.** Emit `chat_history_read_ms`, `chat_history_write_ms`, `node_exception_total{node}` counters; accepted when Prometheus scrape returns non-zero values after a smoke test.
10. **Backfill plan.** One-shot script reads any in-memory deques on shutdown into Postgres; accepted when a rolling deploy preserves at least the last assistant turn for active sessions.
11. **Fallback copy audit.** Replace every `ERROR_FALLBACK_COPY['llm_unavailable']` callsite with the node-attributed message; accepted when grep shows zero unattributed fallbacks on the chat path.

## 6. The one thing only my faculty would have noticed

The deque is a class attribute on `ChatService`, not an instance attribute. Under Gunicorn or uvicorn workers this means every worker holds a separate deque, and the same tenant's two consecutive turns can land on different workers and read different histories. Postgres collapses this accidentally. State that you wanted local-only is already racing across workers; the Nomad restart is just the most visible failure mode. Persistence is not just durability, it is correctness across the worker pool you already deploy.
