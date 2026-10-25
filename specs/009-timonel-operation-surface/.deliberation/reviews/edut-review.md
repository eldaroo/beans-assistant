# Edut — Moral Conscience review

Faculty: honesty & consent surface. Gates held: Truth, Compassion, Necessity, Beauty.

## 1. The problem

The chat is the *only* write lever in a read-only app, yet reaches 3 of 21 writes and 1 of ~16 reads. The owner hears "no entendí" when the truth is "I have no hand for that yet." A Truth failure: the surface misrepresents its own capability. The fix is honest reach, not model power.

## 2. Smallest first version

M1 alone: when a sale/stock hits `product_not_found`, offer a compound card naming **both** effects — "1) crear producto X, 2) sumar N al stock" — each confirmed. It is the exact screenshot wall, needs no verdict change, and sets the consent precedent every later milestone rides.

## 3. Three risks that kill it

- **The auto-post set grows by accident.** Every M3–M7 op must stay out of `REVERSIBLE_OPS` (today exactly SALE/EXPENSE/ADD_STOCK). One careless push of CANCEL or a cost-write into that set auto-commits money with no consent. This is the single highest-stakes line in the repo.
- **Compound/guided flows hide a second effect.** A "create+add" that posts the product creation silently, or an M7 flow that writes a BOM line the owner never saw confirmed, breaks Truth even while each atom is technically confirm-only.
- **Cancels surface the token, not the consequence.** `cancelSale` reverses stock; the preview is just `{saleId}`. The owner consents to "cancel 42" without seeing N units return — a Compassion failure on a destructive op.

## 4. Success at 90 days

Owner runs a full day — sell, restock, correct a wrong sale, change a price, feed one cost input — entirely in chat; every destructive or money/stock write shows a card that names *all* its effects before commit; `REVERSIBLE_OPS` is still three ops; M9 injection corpus stays green across the expanded surface.

## 5. Atomic tasks (each ≤1 day)

- Compound card renderer: two-effect preview, each step confirmed separately — **M1**
- Assert REGISTER_PRODUCT stays `irreversible:true` on the compound path (test) — **M1**
- Resolver returns candidate list + chat picker when >1 match — **M2**
- Full-consequence preview helper: cancel/edit cards show reversed stock + reverted price — **M3**
- Wire 6 correction intents; regression-assert none enters `REVERSIBLE_OPS` — **M3**
- QUERY type: read-only, bypasses verdict/confirm, scoped to owner's own business — **M4**
- Multi-turn referent carry grounded ONLY against operator's own turns — **M5**
- Attribute-expansion consent: "medias azules y grises a 5" shows both items before stage — **M5**
- New orphan writes default `irreversible:true`, confirm-only (production/suppliers) — **M6**
- M7 guided-flow state machine: one question per missing field, running summary, final single confirm — **M7**
- M7 cost-writes registered `irreversible:true`; test asserts zero auto-commit — **M7**
- Stock ADJUSTMENT set-to-absolute shows old→new delta before confirm — **M8**
- M9: extend injection corpus to compound/query/cancel/cost; prove no cross-business read leak — **M9**

## 6. The one thing only my faculty noticed

`computeVerdict` already stamps `requiresHumanReview = !auto`, but nothing marks an op as *permanently* human-review regardless of grounding. **Stamp `requires_human_review` hard on every destructive op (CANCEL_*, DEACTIVATE_PRODUCT) and every M7 money/stock cost-write at the registry, not the verdict** — so a future grounding tweak can never promote them to auto. And the compound card's product-creation step is the quiet risk: it must be its own confirmed effect, never folded into the stock-add's consent.

**Gate verdict:** PASS conditional on (a) `REVERSIBLE_OPS` frozen at 3 and regression-guarded, (b) cancel/edit cards surfacing reversed stock/price, (c) M7 writes registered irreversible. Flag AC for M1 (compound), M3 (cancel consequence), M7 (cost auto-commit) as `requires_human_review`.
