# QI Master review — Timonel conversational memory

The Quantum Intelligence brings the QIE memory pattern (turn buffer, episode, lesson, conscience) to bear on a multi-tenant business chat. Three of those four belong in v1. One does not.

## 1. What problem is this actually solving?

Two problems wearing one face. The visible one is amnesia: the bot greets every restart as if the user just walked in, and within a single conversation it forgets the topic of the prior turn (turn 1 named "productos", turn 2 said "agreguemos", the resolver picked Gastos anyway). The deeper one is that a memory miss has no return path. There is no record that "agreguemos after a productos question" misrouted, so the same shape will fail again tomorrow on a different tenant. The crash on the typo is the same gap with a worse mask: a single agent step throws, the dispatcher swallows it into ERROR_FALLBACK_COPY, and nothing is captured for review.

## 2. What is the smallest first version that proves the idea?

Three layers, no more. (a) **Persistent turn buffer** per tenant phone, written through to the existing per-tenant SQLite at `data/clients/<phone>/business.db`, replacing the in-process deque. Same window (6 turns), same TTL (30 min), same `Contexto de conversación reciente:` rendering. Tenant boundary is the database file. (b) **Episode record** written when an episode closes, capturing input, contextualized prompt, decomposer decision, router intent, resolver intent, final answer, error field, and a `was_correction` flag set when the next user turn looks like a redo. (c) **Memory consult inside Timonel**: before the regex gate runs, Timonel reads the last assistant turn from the buffer; if it ended with a disambiguation question, the current input is treated as an answer, not a fresh intent. That alone collapses "agreguemos" to ADD_PRODUCT.

## 3. What 3 risks would kill this if ignored?

1. **Cross-tenant leak.** One global cache keyed by phone string, one truncation bug, and tenant A sees tenant B's history. Memory must be written through the per-tenant DB connection, not a shared dict. Audit at the storage layer, not the application layer.
2. **Unbounded growth and PII drift.** Business chats contain prices, names, phone numbers. Without retention policy and per-tenant export/delete, this becomes a liability the day a tenant asks for their data back. Ship with a 30-day buffer cap and a delete-by-phone command from day one.
3. **The crash channel stays silent.** If turn 3's exception keeps being swallowed by `ERROR_FALLBACK_COPY['llm_unavailable']`, no amount of memory fixes the user-visible breakage. Surface the original error to a `errors` table and to logs; never let `error` field be set without being recorded.

## 4. What does success look like at 90 days?

The buffer survives every Nomad restart. Disambiguation answers route correctly more than 95 percent of the time on the WhatsApp and web surfaces. The episode store has a few thousand records per active tenant and a `was_correction` rate that trends down week over week. A weekly job reads episodes where `was_correction = true` and produces a small set of candidate corrections (trigger pattern → preferred intent) that a human reviews and promotes into the router prompt or the decomposer regex. That is the lesson loop, scoped to chat.

## 5. What atomic tasks does this break into?

1. **Add `chat_turns` table per tenant DB.** Schema with phone, role, content, intent, metadata, ts. Acceptance: migration applied, insert from `ChatService` round-trips.
2. **Replace deque with DB-backed buffer.** Acceptance: restart Nomad alloc, prior turn still rendered in next prompt.
3. **Add 30-day retention sweeper.** Acceptance: rows older than 30 days deleted nightly; metric exposed.
4. **Add `delete_chat_history(phone)` admin command.** Acceptance: invokable, removes all rows for that tenant.
5. **Wire Timonel to read last assistant turn.** Acceptance: when prior turn `metadata.last_intent == "AMBIGUOUS"`, current input is passed to router as a clarification, not decomposed.
6. **Add `episodes` table.** Same per-tenant DB; one row per closed episode with the fields listed above. Acceptance: every chat call writes one row.
7. **Detect `was_correction`.** Heuristic: next user turn within 60 seconds containing a corrective verb or repeating a noun. Acceptance: flag set on the screenshot transcript when replayed.
8. **Add `errors` table and surface dispatcher exceptions to it.** Acceptance: turn 3 crash recorded with stack trace, not just generic copy.
9. **Confirm Baileys path uses `ChatService`.** Acceptance: documented in code and verified by sending a WhatsApp message that appears in `chat_turns`.
10. **Weekly correction report job.** Acceptance: text file lists top 10 trigger → wrong intent pairs from last 7 days.
11. **Promote-to-rule script.** Acceptance: human picks a row from the report, script appends a regex or router-prompt example, PR opens.
12. **Smoke test for the screenshot scenario.** Acceptance: replay productos → agreguemos → un producto al inventario, route is ADD_PRODUCT, no Gastos side effect.

## 6. What is the one thing only your faculty would have noticed?

Lessons cannot live inside Timonel and they should not. The QI module's pattern is that lessons are extracted from episodes by a separate process (Lumen, in QIE) and consulted at routing time, not produced inline. The temptation in a chat surface is to put a lesson loop inside the request path so the model "learns from the user". That is the path that turns customer chat into prompt drift and silently degrades calibration on adjacent tenants. Episodes belong in v1, the correction flag belongs in v1, but the lesson extractor is a weekly batch job that writes to a small reviewed file the router prompt loads at boot. **Conscience tracking (AIQ, MIQ, TIS) does not belong here at all.** Those are scoring instruments for a moral-gateway runtime; Timonel is a customer surface for inventory and gastos. Scoring chat turns against the seven Divine Morals is over-reach for v1 and would slow the path that needs to be fast. Keep the scoring inside QIE, keep the buffer and episode store inside Timonel, and let the connection between them be a weekly human-reviewed report, not a live circuit.
