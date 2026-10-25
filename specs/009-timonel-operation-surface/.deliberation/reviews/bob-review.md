# Bob (Scrum Master) — review: Timonel full operation surface

## 1. What problem is this actually solving
The chat is the *only* write/correct lever in a 100%-read-only app, yet it reaches 3 of 21 writes, 1 of ~16 reads, 0 of 6 corrections. The owner can't operate his own business by conversation. This is a **wiring and sequencing** problem, not a model-power problem — most commit logic already exists in `lib/ops/registry.ts` (9 ops live) and the GET routes already exist; the parser just never emits the intents and the chat route never dispatches the reads.

## 2. Smallest first version that proves the idea
M1 + M4 shipped together. M1 (product_not_found → 2-step REGISTER_PRODUCT→ADD_STOCK confirm card) fixes the exact screenshot, ~3 files, zero verdict change. M4 (QUERY read-dispatch to the ~15 existing reads) is pure wiring — new non-verdict path. Neither needs a keystone built. Together the owner immediately feels "it answers me and lets me do the thing" with the least new code.

## 3. Three risks that would kill this
- **M7 scope creep blocking cheap wins.** The cost-model guided flows (8 interdependent writes, multi-turn) are the heaviest work. If sequenced early or kept as one cohort it starves M1–M4. Isolate it late; split it.
- **M5 multi-turn re-opening the stateless spine.** History-in-request is easy to let drift into server-side session state, which breaks the hard constraint. The grounding rule (numerals only against the operator's own turns) must be an AC, not a nicety.
- **M9 deferred.** Injection hardening must gate the *expanded* surface (cancel/edit/cost auto-commit, cross-business read leaks). If it slips, every new intent ships unproven.

## 4. Success at 90 days
Owner runs a full day — register, correct a mistake ("cancela la venta 42"), ask "cuanto vendi hoy", feed the cost model by chatting — without touching a table. m7-injection/posture/parity still green over the whole surface. Undo survives a refresh. Zero DB credential or tool ever reaches the model.

## 5. Atomic tasks (each ≤1 day)
1. [M1] chat route + chat.tsx: product_not_found emits chained REGISTER_PRODUCT→ADD_STOCK confirm card.
2. [M1] chat.tsx sequential-confirm card UI for a 2-step proposal.
3. [M4] add QUERY kind to `lib/parse/types.ts` + fallback intents; no verdict/no confirm.
4. [M4] chat route: dispatch QUERY → existing domain read fn.
5. [M4] map the ~15 NL questions to existing GET/domain reads.
6. [M2] reference resolver: "la ultima venta"/"la venta de Juan"/"las medias" → numeric id.
7. [M2] disambiguation picker (candidateCount>1) in chat route + chat.tsx.
8. [M3] parser intents CANCEL_SALE/CANCEL_EXPENSE/CANCEL_STOCK, riding M2 resolver.
9. [M3] parser intents UPDATE_PRICE/DEACTIVATE_PRODUCT, riding M2.
10. [M5] carry history in request; server grounds numerals only against operator's own turns.
11. [M5] attribute expansion ("medias azules y grises a 5" → 2 items).
12. [M6] new ops+intents: recordProduction, createSupplier, recordCheckin, product non-price edit.
13. [M7] guided-flow slot-filling framework on M5 + first 4 costing writes.
14. [M7] remaining 4 costing/logistics writes (customs, indirect pool).
15. [M8] aggregation reads + stock ADJUSTMENT intent; durable recent-ops list so Undo survives refresh.
16. [M9] run m7-injection corpus over compound/query/cancel/edit/cost flows.

## Cohort boundaries (≤10 children, each a shippable owner-visible increment)
- **Cohort 1 — cheap wins:** M1 + M4 (tasks 1–5). No keystone needed; ships first.
- **Cohort 2 — correct by chat:** M2 + M3 (tasks 6–9). Keystone 1 + its only dependent.
- **Cohort 3 — complete across turns + more writes:** M5 + M6 (tasks 10–12). M5 is keystone 2 for M7.
- **Cohort 4 — cost model by chat:** M7 (tasks 13–14). Heaviest; isolated so it never blocks 1–3.
- **Cohort 5 — reads, durable undo, hardening:** M8 + M9 (tasks 15–16). M9 must be last to cover the whole surface.

**Order to maximize early value:** M1+M4 before the keystones — M4 read-dispatch has **no dependency on M2** (reads don't need ids), so it's the cheapest high-value win and should not wait behind reference resolution.

## 6. The one thing only my faculty noticed
The plan implies M2→M3→M4 in sequence, but **M4 does not depend on M2.** Read-dispatch is self-contained wiring; only cancels/edits need the resolver. Pulling M4 forward into cohort 1 buys the owner "it answers me" a full cohort earlier. And **M7 is the only milestone too big to be one cohort** — 8 interdependent writes + a new multi-turn framework will exceed 10 children; split it M7a (framework + 4 writes) / M7b (remaining 4), or it becomes the cohort that never honestly drains.
