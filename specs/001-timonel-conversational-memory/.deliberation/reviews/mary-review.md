# Mary review — Timonel conversational memory + crash bound-fix

## 1. What problem is this actually solving?

The stated request is "give Timonel memory and check why it crashed". The real problem is two-layered.

Layer one is a **state ownership gap**. The decomposer (Timonel) sits at the entry of the LangGraph but has zero awareness of prior turns. The only memory in the system is a class-level deque inside `ChatService`, scoped to one FastAPI process, lost on every Nomad restart, and only reachable by the web widget surface. WhatsApp goes through a separate dispatcher path that nobody on the team can confidently say shares this deque. So memory is partial, fragile, and surface-coupled, not a property of the agent graph.

Layer two is **front-end semantic coupling masquerading as agent behavior**. The widget's `inferNavigation()` is a keyword scan over the assistant's reply text. When the assistant asks the disambiguation question "una venta, un gasto, un producto nuevo o stock", the widget reads the word "gasto" and opens the Gastos tab. The agent never picked an intent; the UI did. This is a critical finding for problem framing because Dario currently reads the bug as "Timonel chose wrong" when the agent actually behaved correctly and the front-end overrode it.

The user-visible symptom is loss of trust: the bot ignores what was just said and the UI does things the user never asked for.

## 2. What is the smallest first version that proves the idea?

A persistent, multi-tenant-keyed conversation log table (`chat_history` per tenant DB) plus a single graph-level `recent_turns` slice loaded into `AgentState.metadata.history` at the entry of the graph, before the decomposer. Decomposer reads it. Router already reads it (the prompt is wired). One write at the end of every turn, success or failure. No embeddings, no episodic store, no cross-channel sync yet. Just durable, graph-native, multi-tenant turn history that survives a Nomad restart and is shared across web and WhatsApp because both surfaces hit the same graph.

Bound-fix to ship in the same PR: replace `inferNavigation()` keyword scan with a `metadata.navigation` field set by the agent only when it actually executed a tool, and surface a typed `error_code` from the backend so the widget stops swallowing real exceptions into "No pude procesar tu mensaje ahora".

## 3. What 3 risks would kill this if ignored?

1. **Multi-tenant leakage.** History keyed by phone with no tenant scope check. One bug in `tenant_context()` and conversation A surfaces inside conversation B. Hard requirement: history reads MUST go through `tenant_context()`, never the class-level dict.
2. **Context-window bloat.** Six turns is fine. Sixty turns dragged into every Anthropic call doubles cost and pushes latency past the user's patience. Need a token budget and a summarization fallback before we let history grow.
3. **History poisoning the router.** A bad disambiguation marker from a prior turn can lock the next turn into the wrong intent. Need a kill-switch (per-tenant flag) and a "clear context" user gesture that wipes the slate.

## 4. What does success look like at 90 days?

- Zero "memory lost" incidents reported by Dario or by tenant onboarding sessions across web and WhatsApp.
- Disambiguation collapse rate: ≥ 80% of turns following an AMBIGUOUS turn resolve without re-asking.
- Crash copy ("No pude procesar tu mensaje ahora") fires at < 0.5% of turns, with every occurrence carrying a structured `error_code` Sentry can group.
- Median context-injection cost stays under 400 input tokens per turn at p95.
- One regression test per shipped fix, runnable in CI.

## 5. Atomic tasks

1. **Add `chat_history` table to tenant DB schema.** Acceptance: migration creates table with `phone`, `turn_id`, `role`, `content`, `metadata_json`, `created_at`; runs against SQLite and Postgres.
2. **Write `ConversationStore` service.** Acceptance: `append(phone, turn)` and `recent(phone, limit)` go through `tenant_context()`; in-process deque removed.
3. **Inject history into `AgentState` at graph entry.** Acceptance: new node `load_history` populates `metadata.history` before decomposer; existing context-injection in `chat_service` deleted.
4. **Decomposer reads history for ambiguity collapse.** Acceptance: when prior assistant turn was AMBIGUOUS, decomposer skips re-classification and forwards the resolved intent.
5. **Router prompt unchanged, validated against new path.** Acceptance: existing router tests pass; new test asserts `Contexto de conversación reciente:` block reaches router.
6. **Replace `inferNavigation()` with `metadata.navigation`.** Acceptance: widget no longer keyword-scans reply text; agent emits `navigation` only on confirmed tool execution.
7. **Surface typed `error_code` from backend on graph exception.** Acceptance: chat endpoints return `{error_code, response}`; widget renders `ERROR_FALLBACK_COPY[error_code]`, never the bare catch-all.
8. **Wrap decomposer/resolver/write_agent in node-level try-except.** Acceptance: any node exception returns a state delta with `error_code` and a Spanish user-facing line; graph never raises to the API layer.
9. **Add typo-tolerant intent fuzzing in resolver.** Acceptance: "prodcuo", "ptodu", "prdocto" all resolve to `producto`; covered by parametric test.
10. **Add per-tenant `clear_context` endpoint and widget gesture.** Acceptance: button wipes history for that phone; next turn classifies cold.
11. **Token-budget the history block.** Acceptance: history truncated to 1500 input tokens; oldest turns dropped first.
12. **Sentry tag `error_code` and `intent` on every chat exception.** Acceptance: errors group by code in Sentry dashboard.
13. **Regression test: turn 1 names topic, turn 2 says "agreguemos", expect `REGISTER_PRODUCT` not `REGISTER_EXPENSE`.** Acceptance: test passes against new history-aware decomposer.
14. **Regression test: turn 3 with typo "prodcuo" returns a clarifying question, not the generic crash copy.** Acceptance: response contains "¿Qué producto" and `error_code` is null.

## 6. The one thing only my faculty would have noticed

The Gastos side-effect on turn 2 is **not an agent failure**. It is the front-end's `inferNavigation()` keyword router firing on the word "gasto" inside the bot's own disambiguation question. The assistant text is "una venta, un gasto, un producto nuevo o stock" and the widget greps that text for navigation triggers. Memory will not fix this. The keyword router will keep mis-triggering on any disambiguation reply that lists options by name. Spec must include: replace text-scan navigation with structured `metadata.navigation` set by the agent only when a tool actually executed. Without this, the user keeps getting yanked into wrong tabs and will blame the new memory feature for behavior that predates it.
