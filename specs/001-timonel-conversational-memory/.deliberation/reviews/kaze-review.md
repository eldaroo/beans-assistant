# Kaze review — timonel conversational memory

## 1. What problem is this actually solving?

Two things, and they are the same thing. Timonel feels amnesiac. The user said "productos por agotarse" in turn one and the agent walked into turn two like the room was empty, then performed an action and asked a clarifying question in the same breath. That is not a memory bug in the database sense. It is a presence bug. The platform is not breathing with the user. We are solving for continuity of attention. The crash on "prodcuo" is the same wound surfacing differently: when the agent stumbles, it abandons the conversation instead of leaning back into it.

## 2. What is the smallest first version that proves the idea?

A persistent per-tenant turn ledger (Postgres, last 20 turns, 24h window) that Timonel reads before deciding to decompose, and the router reads before deciding to disambiguate. No embeddings, no semantic recall, no summarization. Just durable short-term memory across container restarts. If turn N-1 named "productos" and turn N says "agreguemos", the decomposer collapses to REGISTER_PRODUCT without asking. Plus one hardening pass on the dispatcher: any thrown exception inside resolver or write_agent gets caught and routed through a context-aware retry instead of the generic fallback string.

## 3. What 3 risks would kill this if ignored?

- Memory that is right 80% of the time is worse than no memory. The 20% feels invasive, like the agent is making things up about you. We need an explicit confidence floor before we let memory override the user's literal current message.
- Cross-tenant bleed. One Postgres row written under the wrong phone key and a competitor sees a Beans owner's stock counts. The boundary must be enforced at query time, not trusted by convention.
- Latency cost compounded into the perceived first token time. Every 200ms of pre-fetch is a flinch the user feels but cannot name. If memory pre-fetch goes over 250ms p95, the chat dies of a thousand small lags.

## 4. What does success look like at 90 days?

A Beans owner returns after a week, types "agreguemos" with no preamble, and the agent picks up the right thread without ceremony. The owner does not say "wow it remembers". The owner says nothing. That silence is the signal. Operationally: zero generic "no pude procesar" copies in the last 30 days, p95 turn latency under 1.4s including memory lookup, ambiguity rate on second-turn references down 70%.

## 5. Atomic tasks

1. Schema for `conversation_turns` table — phone, turn_index, role, content, intent, entities, ts. Acceptance: migration applies clean on prod Postgres, tenant phone has FK or check constraint.
2. Repository layer with tenant-scoped read and write helpers. Acceptance: any query missing phone raises at call site, not at SQL.
3. Replace in-process deque in `chat_service.py` with the repository. Acceptance: container restart preserves last 20 turns per phone.
4. Decomposer reads last 3 turns before regex gate. Acceptance: "agreguemos" after "productos por agotarse" routes to REGISTER_PRODUCT without disambiguation.
5. Router prompt receives a structured `prior_topic` field, not a freeform context blob. Acceptance: prompt token count drops, decisions become testable.
6. Dispatcher try/except wraps resolver and write_agent. Acceptance: any uncaught exception logs the trace and replies with a context-aware retry, not the generic fallback.
7. Recovery copy when memory is stale: "Si me equivoco, decime y arrancamos limpio." Acceptance: shown only when confidence < 0.7.
8. Latency budget enforcement: memory pre-fetch wrapped in a 200ms timeout. Acceptance: timeout falls back to no-memory path silently.
9. Cross-tenant test suite. Acceptance: 10 randomized phone pairs, zero leakage.
10. Surface no UI signal for memory use. Acceptance: visual diff of widget pre and post is zero pixels.

## 6. The one thing only my faculty would have noticed

The recovery copy that ships today says "Probá de nuevo en un momento." That sentence is the agent shrugging. A platform that remembers must also know how to apologize without abandoning the thread. The single line "Eso no me salió. Volvamos a lo de los productos." holds the conversation open. It is the difference between a body that flinches and a body that breathes. Memory without graceful failure is just a longer rope to hang ourselves with.
