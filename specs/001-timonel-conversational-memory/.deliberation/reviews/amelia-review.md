# Amelia review — timonel conversational memory

## 1. What problem is this actually solving

Two distinct problems share one root cause: the graph has no durable memory and no per-node fault isolation. The Turn 2 collapse (Gastos opened while bot also asked for clarification) is a memory miss. Turn 1 named the topic (productos), Turn 2 said agreguemos, but the decomposer and router never saw Turn 1 because the in-process deque in `ChatService` is the only memory and the side-effect dispatcher fires before the resolver settles. The Turn 3 crash on the typo prodcuo is a fault-isolation miss: the resolver or write_agent threw, the exception bubbled through `_invoke_graph`, the front-end mapped it to `llm_unavailable`. The user got generic copy that hides the actual failure mode (typo to a product not in catalog).

## 2. What is the smallest first version that proves the idea

Persist the existing `ChatService._history_by_key` deque to SQLite under `data/clients/<phone>/business.db` in a new `chat_history` table (turn_no, role, content, metadata_json, created_at). On chat_service load, hydrate the deque from the last `CHAT_CONTEXT_MAX_TURNS * 2` rows for that phone. Keep `_build_message_with_context` and its `Contexto de conversacion reciente:` prefix unchanged. Wrap each graph node in a `safe_node` decorator that catches exceptions and writes a typed `error_class` to state. That is the v1: same prefix string the router already understands, plus persistence, plus a typed error envelope.

## 3. What 3 risks would kill this if ignored

a. Tenant-boundary leak. `_history_by_key` is process-wide. If we move it to disk without the `tenant_context()` wrapper, one tenant's history can land in another tenant's DB. Every read and write must go through `tenant_context(resolved_phone)`.
b. Schema drift between WhatsApp and web. Baileys connector calls `chat_with_tenant` too, but if any code path skips `_invoke_graph`, that channel writes nothing to history and reads nothing back.
c. Prompt bloat. Persisting raw history beyond `CHAT_CONTEXT_MAX_TURNS` and feeding all of it into the router prompt will silently push us over context windows on the cheap LLM (Haiku-class) used by the decomposer.

## 4. What does success look like at 90 days

Container restart no longer wipes any conversation. Turn 2 of the bug transcript classifies as REGISTER_PRODUCT or ADD_STOCK because Turn 1 carries the topic forward. The Gastos UI flip never fires from a router-level AMBIGUOUS. Generic `llm_unavailable` copy disappears from logs except for true LLM 5xx; typos route to a `unknown_product` Spanish copy that names the candidate.

## 5. Atomic tasks (each ≤ 1 day)

1. Add `chat_history` SQLite table and migration. Acceptance: migration runs idempotently per tenant on `tenant_context` open.
2. Repository `ChatHistoryRepo` with `append(role, content, metadata)` and `recent(limit)`. Acceptance: 6 unit tests cover insert, ordering, limit, tenant isolation.
3. Wire `ChatService._append_history` and `_build_message_with_context` to the repo. Acceptance: existing `test_chat_service_ambiguity.py` passes unchanged.
4. Extend `AgentState` with one field `memory: Optional[Dict[str, Any]]` carrying `{recent_turns, pending_entities, last_intent}`. Acceptance: typecheck clean, no node signature changes.
5. New node `memory_loader` between entry and `decomposer`. Acceptance: populates `state["memory"]`, never throws.
6. Decompose `should_decompose` to also accept `memory.last_intent` to break ties. Acceptance: new eval cases for the agreguemos transcript.
7. `safe_node(name)` decorator that catches and writes `state["error"] = {"class": ..., "node": name, "msg": ...}`. Acceptance: unit test per node confirms exception becomes typed error.
8. Map `error.class` to Spanish copy in `_compute_per_sub_input_answer`. Classes: `typo_or_unknown_product`, `missing_field`, `network`, `llm_unavailable`. Acceptance: 4 tests, one per class.
9. Patch `chat_widget.js` to surface `error.class` instead of always `llm_unavailable`.
10. Eval suite extension: add the bug transcript verbatim to `tests/eval/router_ambiguity.json` and the typo case to a new `tests/eval/typo_recovery.json`.
11. Backfill task: one-time script copies any in-process deque to the new table on boot. Acceptance: idempotent, logs row count.
12. Remove the dispatcher side-effect that flips UI to Gastos before resolver completes. Acceptance: regression test for Turn 2.

## 6. The one thing only my faculty would have noticed

`_invoke_graph` calls `_build_message_with_context` and overwrites `state["user_input"]` with the prefixed string before the decomposer runs. The decomposer's regex gate (`LIST_SEPARATOR`, `ACTION_VERBS`) then runs against `Contexto de conversacion reciente: ...\nMensaje actual: agreguemos`. `agreguemos` alone has zero verbs and zero list separators, so the gate passes through. But the prefix can introduce false positives: a prior turn containing `vendi 5 y compre 3` will trip `ACTION_VERBS` on the context, not the new message. Fix: the decomposer must read `state["memory"]["current_message"]` for gating, not the contextualized blob. This is a one-line bug today, hidden because the test set runs without history.
