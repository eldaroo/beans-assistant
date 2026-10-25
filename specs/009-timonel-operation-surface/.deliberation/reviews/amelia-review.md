# Amelia — Developer review (BuildOS)

Grounded in the live 008 `web/`.

## 1. The problem
Chat is the app's only write lever (every `page.tsx` is read-only), yet reaches 3 of 21 writes, 1 of ~16 reads, 0 of 6 corrections. The dead end is missing *orchestration* around a stateless parser, not model power. Correct problem.

## 2. Smallest first version
M1, scoped honestly (see §6): "50 pulseras rojas" → one card offering "crear producto + cargar stock," chained client-side over existing `/ops/stage`+`/confirm`. Proves the thesis (feel of power, powerless model) in three files.

## 3. Three risks
- **M7 is not 8 wirings.** The costing writes are interdependent (`recordBomLine` needs a `productId` *and* a `costInputId` from `recordCostInput`, plus country enum + quantity). They are meaningless as single-shot proposals; M7 cannot ship before M5's guided-flow substrate exists. Sequencing M7 as "cheap, fn exists" will blow up.
- **verdict.ts provenance breaks multi-turn.** `numeralIsGrounded` checks the numeral against *one* utterance. "vendi 40 stanleys" then "a 32" splits product and price across turns, so M5 flows never auto-post unless grounding re-reads the operator's own flow turns — otherwise every multi-turn write silently drops to confirm-only.
- **No conversation state exists.** `turnNonce` is minted fresh per send (`chat.tsx:49`); no conversationId, no history, no flow table. M5 is a real build, not a restore.

## 4. Success at 90 days
Owner runs a full day — sales, a cancel, a price change, "cuánto vendí hoy," seeds one product's cost model by chatting — never touching a table or the DB. m7-injection/m7-posture still green over compound/query/cancel/guided flows.

## 5. Atomic tasks
- **M1** `web/lib/ops/stage.ts`: on `candidateCount===0`, return structured `{code:"product_not_found", ref, pendingIntent:{op,args}}` instead of a bare message.
- **M1** `web/app/(app)/_components/chat.tsx`: stop rendering every `!r.ok` as "Error:"; detect `product_not_found` and render a 2-step compound card that sequences stage→confirm(REGISTER_PRODUCT) then stage→confirm(ADD_STOCK).
- **M1** `web/lib/ops/registry.ts`: let `REGISTER_PRODUCT.resolve` mint a name-only minimal product (derive sku, `unitCostCents:0`); add `summarize` branch for REGISTER_PRODUCT in `chat.tsx`.
- **M2** `web/lib/ops/resolve-ref.ts` (new): resolve "la última venta"/"la venta de Juan"/"el gasto de luz" to an id via `listSales`/expense reads; return candidates for >1.
- **M2** `web/app/(app)/_components/chat.tsx`: disambiguation picker card ("¿cuál? 1)… 2)…") feeding the chosen id back into staging.
- **M3** `web/lib/parse/fallback.ts` + `deploy/beans-parse.nomad.hcl` SYS: emit CANCEL_SALE/EXPENSE/STOCK, UPDATE_PRICE, DEACTIVATE_PRODUCT intents (commit+verdict already in `registry.ts`).
- **M4** `web/lib/ops/query.ts` (new): QUERY dispatch map intent→domain read fn (`salesSummary`, `directory`, `pendingCustoms`, landed cost), no verdict/confirm. Do NOT reuse GET handlers — they return `Response` and call `guard()`; call domain fns directly.
- **M4** `web/app/api/chat/route.ts`: branch QUERY before `stageOperation`; per-question Spanish formatters (the real M4 cost, not the data).
- **M5** `web/lib/flow.ts` (new) + `web/db/schema` flow table: stable conversationId + operator-turn history; `chat.tsx` carries it in the request.
- **M5** `web/lib/verdict.ts`: ground numerals against the active flow's operator turns, not a single utterance; named test `m7-injection.mts` extended to prove no cross-turn hijack.
- **M6** `web/lib/ops/registry.ts` + `fallback.ts`: ops for `recordProduction`, `createSupplier`, `recordCheckin`, non-price `updateProduct` (small, all confirm-only).
- **M7** `web/lib/flow/cost-intake.ts` (new): guided multi-turn flow over the 8 costing writes; depends on M5.
- **M8** `web/app/api/ops/recent/route.ts` (new) + `chat.tsx` load-on-mount: recent-committed list from `pending_ops WHERE status='COMMITTED'` so Undo survives refresh.
- **M9** `web/scripts/m7-injection.mts`: extend corpus over the new flows.

## 6. The one thing only my faculty noticed
M1's compound card **cannot fire today**: `product_not_found` returns through `fail()`, and `chat.tsx` collapses every `!r.ok` into a red "Error:" string. The error channel must first become a structured, actionable payload. The plan's "zero parser/verdict change, ~3 files" is true but hides a product-minting decision (no SKU/cost in "50 pulseras rojas") and an error-contract change — correctly sized at 3 files, mis-described as trivial.
