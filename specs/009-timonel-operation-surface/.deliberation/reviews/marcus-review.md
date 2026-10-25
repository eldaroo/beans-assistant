# Marcus — Financial Modeler review

Spec 009, financial lens: the cost model (M7), aggregation reads (M8), numeral grounding.

## 1. The problem
The costing dashboard is a correct, disciplined engine that no owner can feed. `costing.ts` holds a six-component landed cost with real conservation rules — pending components are excluded, never summed as zero (`recompute`), and margin is `null` until the cost is complete *and* a price is set (`margin`). But all eight write paths (`recordCostInput`…`recordIndirectPool`) are reachable only by DB seed. The real problem: put interdependent cost data into a conversational channel without letting the owner build a cost that *looks* complete but isn't, and without the model inventing an FX rate or a USD figure.

## 2. Smallest first version that proves it
One guided flow that lands a single real landed cost: `recordCostInput` → `recordInputPurchase` (FX→USD) → `recordBomLine`, then show the product's landed cost flipping from "parcial · falta Materiales" to a real number. If the pending-never-zero math survives a conversational entry and the FX conversion is grounded, M7 is proven; the other five writes are the same pattern.

## 3. Three risks that would kill it
- **Derived numbers can't be grounded verbatim.** `numeralIsGrounded` only passes a numeral the operator *typed*. `usdCentsFrom(original/fx)` is derived — it will never match the utterance. Ground the *inputs* (original amount, fx rate, quantity) the owner spoke; let the app own the USD. Get this backwards and either grounding rejects every purchase or you ground a model-fabricated USD.
- **Period aggregations breaking ledger conservation.** `expenses_total` nets `CANCELACION` rows negatively. A naïve new "expenses by category/month" that `SUM`s by category will surface CANCELACION as a positive bucket *and* leave the original uncancelled — double error. New queries must carry the same sign convention.
- **False-complete cost.** If a guided flow lets the owner skip shipping/customs (legitimately `null`+note today) but the UI reads it as done, margin shows a confident wrong number. The `parcial` floor must stay visible end-to-end.

## 4. Success at 90 days
The owner has built at least one product's full landed cost across all three countries by chatting — no admin form — and the costing page shows real margins. Monthly profit/revenue answer in chat for an arbitrary month, matching a hand check to the cent. Zero cost-write committed with an ungrounded or model-supplied amount (M9 corpus proves it).

## 5. Atomic tasks
- Define cost-entry dependency order + enforce FK prereqs (product→input→purchase→BOM); inline-create a named-but-unknown cost input. **M7**
- Guided-flow state machine honoring partial order via pending-never-zero (any order, recompute names gaps). **M7**
- Ground FX purchase on *spoken inputs* (original amount + fx + qty), app derives USD; confirm card shows derivation. **M7**
- Parser intents + ops for the 8 cost writes (all irreversible → confirm-only). **M7**
- `recordLaborBatch` completed-basis + `recordIndirectPool` cross-dep on production record; flag missing production. **M7**
- Period-revenue query over `sales_summary` by day-range. **M8**
- Period-profit = period revenue − period expenses (new expense-by-period query). **M8**
- Expense-by-category/period query preserving CANCELACION sign. **M8**
- Stock ADJUSTMENT set-to-absolute intent. **M8**
- M9 corpus over guided-cost flows: no fabricated fx/USD auto-commits. **M9**

## 6. The one thing only my faculty noticed
A multi-field FX cost entry spoken across turns ("50000 pesos" / "a 4000 por dólar") cannot be grounded by the current guard: `numeralIsGrounded` checks one utterance, and the only number that matters downstream — the derived USD unit cost — was never typed at all. M7 must ground the operator's *own-turn union of inputs* (M5), never the computed USD, and the app alone may run `usdCentsFrom`. Otherwise the costing engine's hard-won pending-never-zero honesty is undermined at the point of entry.
