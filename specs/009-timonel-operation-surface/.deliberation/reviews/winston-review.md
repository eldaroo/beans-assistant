# Winston — review: Timonel full operation surface (spec 009)

**1. What problem is this actually solving.**
The whole app is read-only tables; `web/app/(app)/_components/chat.tsx` + `/api/chat` is the *sole* write and correct lever, and it is almost entirely unwired — 3/21 writes, 1/16 reads, 0/6 corrections reach it. The owner hit `product_not_found` with no next step and read the app's powerlessness as the model's. The spine (stateless propose-only parser → app verdict → non-model `/confirm`) is correct and proven; spec 009 is *wiring*, not a new brain. The powerlessness is deliberate in the model and accidental in the app — close only the second.

**2. Smallest first version.**
M1, exactly as scoped: the `product_not_found` branch in `lib/ops/stage.ts` returns a two-step compound card (REGISTER_PRODUCT then ADD_STOCK), rendered and confirmed in order in `chat.tsx`. Zero parser/verdict change. It proves compound-as-UX and the screenshot heals, before the `Proposal` contract is touched.

**3. Three risks that would kill this.**
- **Compound atomicity lie.** If widening `Proposal` to a list makes a turn commit atomically, a late step's failure strands an early irreversible commit — there is no cross-step transaction in `/confirm`. Step must stay the commit unit.
- **Grounding corpus poisoning.** M5 history-in-request: if `computeVerdict` grounds numerals against the *assistant's* prior replies or any non-operator text, D-041 provenance collapses and injection re-opens on the write path.
- **Model-supplied ids.** If the parser emits `saleId` for a cancel, a hijacked model deletes sale #999. Ids must be server-derived.

**4. Success at 90 days.**
All 21 writes, 6 corrections, ~15 reads reachable from chat; the owner runs the business end-to-end conversationally; the costing dashboard is feed-able by talking to Timonel; `m7-injection.mts`/`m7-posture.mts` stay green over compound/query/cancel/edit/cost flows, with new cases proving no read leaks cross-business data and no resolver can be hijacked by operator text.

**5. Atomic tasks (each ≤1 day).**
- T1 (M1) `product_not_found` → 2-step compound card payload, app-side.
- T2 (M1) `chat.tsx` multi-step card: confirm in order, thread step-1 result id into step-2 args.
- T3 (M2) server-side resolvers `resolveSale/Expense/StockMovement` (descriptor → id | candidates), mirroring `resolveActiveProduct`.
- T4 (M2) disambiguation picker payload + UI; each option carries the *server-resolved* id.
- T5 (M3) parser intents + registry wiring for CANCEL_SALE/EXPENSE/STOCK, UPDATE_PRICE, DEACTIVATE_PRODUCT, riding T3.
- T6 (M4) QUERY kind as a discriminated union on `Proposal`; read-only registry; chat route branches *before* `stageOperation`.
- T7 (M4) wire the ~15 existing domain reads into the read registry with NL dispatch.
- T8 (M5) `/api/chat` accepts a bounded operator transcript; assemble active-flow operator turns.
- T9 (M5) per-flow provenance in `computeVerdict`: ground against the union of operator turns only; exclude assistant turns.
- T10 (M6) new ops recordProduction/createSupplier/recordCheckin + updateProduct non-price + intents (all irreversible→confirm).
- T11 (M7) app-side guided-flow controller (missing-field loop) for the 8 cost writes; per-step propose-only.
- T12 (M7) cost ops in registry (irreversible) + reference resolution for input/BOM dependencies.
- T13 (M8) aggregation reads (monthly/range profit+revenue, expense-by-category/period) + stock ADJUSTMENT set-to-absolute.
- T14 (M8) durable recent-committed-ops read from `pending_ops` COMMITTED → Undo survives refresh.
- T15 (M9) run injection/posture corpus over the expanded surface; add leak + resolver-hijack cases.

**6. The one thing only my faculty noticed.**
`pending-ops.ts` *already* implements the compound substrate: `turnNonce` correlates many staged ops to one turn and `verdictPendingForTurn` returns an ordered **list**. Only `Proposal` and the chat route are singular. Widening to a list finishes a half-built mechanism — which is why step-as-commit-unit is free and atomic-compound is the regression. The inverse is the trap: QUERY must touch *none* of that substrate, or a read inherits the write path.
