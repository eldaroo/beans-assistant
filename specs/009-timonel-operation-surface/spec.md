> Tracked as eldaroo/beans-assistant#240

---
date: 2026-10-24
status: draft, ready to /develop
target_repo: eldaroo/beans-assistant
base_branch: claude/008-vercel-migration
run_id: timonel-operation-surface-20261024-174517
---

# Spec 009: Timonel full operation surface

> Connect every business operation to the conversational assistant, inside the propose-only architecture.

## Problem

Beans runs on a single conversational lever. Every one of the nine module pages in the live app (`web/app/(app)/*/page.tsx`) is a read-only table with no action buttons, so the Timonel chat is the only place the owner can write or correct anything. That lever is almost entirely unwired: of 21 domain write functions it reaches 3 (sale, expense, add-stock), of about 16 natural owner questions it answers 1 (cost scenario), and of 6 built-in correction and edit operations it reaches 0. The owner logged in, typed "me entraron 50 pulseras rojas", got `product_not_found`, typed "dale, registralo", and got "No pude interpretar eso como una operacion". He read the app's powerlessness as the model's.

It is not the model's. A three-agent investigation and a two-agent surface audit, both grounded in the live code, found that the dead end is a missing app-orchestration layer, not a missing model capability. The stateless, tools-off, propose-only parser is the correct spine and is proven safe by `web/scripts/m7-injection.mts` and `web/scripts/m7-posture.mts`. Spec 009 is wiring and orchestration on top of that spine, never a new brain.

## Why now

The owner is using the live app and hitting the wall every day. The commit layer for corrections already exists in `web/lib/ops/registry.ts` (nine ops with verdict and undo), the read data already exists behind GET routes and domain functions, and the compound substrate is half-built (`web/lib/pending-ops.ts` already correlates many staged ops to one `turnNonce` and returns an ordered list). The work is mostly connecting what is already there. Doing it now, before more owners onboard, turns a demo into a tool the owner can run his whole business from by talking.

## Scope

### In scope

- Compound proposals: the parser response becomes an ordered list of steps, each step staying its own commit unit (one op_token, one verdict, one confirm).
- The screenshot fix: a product-not-found on a stock or sale offers a two-step create-then-act confirm card.
- Server-side reference resolution so "la ultima venta", "la venta de Juan", "las medias", "el gasto de luz" resolve to an id, with a disambiguation picker when more than one matches.
- The six already-built correction and edit ops reachable by natural language: cancel sale, cancel expense, cancel stock, update price, deactivate product, register product.
- A read-only QUERY proposal kind dispatched off the write path, wiring the roughly 15 owner questions whose data already exists.
- Multi-turn context carried in the request with grounding bounded to a server-authenticated record of the operator's own turns; attribute expansion.
- Orphan operational writes: production record, supplier create, supplier check-in, product non-price edit.
- Cost-model data entry as app-orchestrated guided conversational flows over the eight costing and logistics writes.
- New aggregation reads: monthly and date-range profit and revenue, expense by category and by period, stock adjustment to an absolute count; a durable recent-committed-ops list so Undo survives a page refresh.
- Injection and posture hardening over the whole expanded surface.

### Out of scope

- Giving the model tools or DB credentials. That is spec 007's native tool-use gateway, retired at the spec-008 cutover; it is not reopened by this spec.
- Any UI action buttons on the module pages. The pages stay read-only; chat stays the write lever. Adding page-level controls is a separate capability outside this arc.
- A general-purpose server-side conversation or session store beyond the lightweight operator-turn grounding record this spec defines.
- The spec-008 M8 production cutover (DNS, auth, retiring the Python app). That is a separate, already-tracked gate.

## Acceptance criteria

1. On a stock or sale whose product does not resolve, `web/app/api/chat/route.ts` returns a structured compound proposal of two ordered steps (REGISTER_PRODUCT then ADD_STOCK or the sale), not a bare error string; `web/app/(app)/_components/chat.tsx` renders one card showing both effects and confirms them in order, threading the created product id into the second step. (M1)
2. `REGISTER_PRODUCT.resolve` in `web/lib/ops/registry.ts` mints a minimal product from a name alone (derived sku, unit cost 0, price pending) so a name-only utterance can create a product. (M1)
3. `Proposal` in `web/lib/parse/types.ts` is an ordered list of steps; each step is resolved, verdicted, staged, and committed independently through the existing `/api/ops/confirm`; there is no cross-step atomic transaction. A named test asserts a late-step failure leaves earlier committed steps intact and does not strand a partial. (M1)
4. New resolvers `resolveSale`, `resolveExpense`, `resolveStockMovement` in a new `web/lib/ops/resolve-ref.ts` turn an operator descriptor into `{candidateCount, id, candidates}`; the parser emits descriptors only and never a numeric id; a named test asserts a caller-supplied id is rejected by the cancel and edit paths. (M2)
5. When reference resolution returns more than one candidate, the chat returns a disambiguation picker and each option carries the server-resolved id; selecting one re-enters staging with that id. (M2)
6. The parser (`web/lib/parse/fallback.ts` and the `deploy/beans-parse.nomad.hcl` SYS prompt) emits CANCEL_SALE, CANCEL_EXPENSE, CANCEL_STOCK, UPDATE_PRICE, DEACTIVATE_PRODUCT; each stages and shows a confirm card that surfaces the full consequence (reversed stock, reverted price) before confirm; none auto-posts. (M3)
7. Destructive and cost-model ops carry a permanent `requiresHumanReview` flag at the registry level in `web/lib/ops/registry.ts`, independent of the dynamic verdict, so no future grounding change can promote them onto the auto-post path; a named test asserts each stays confirm-only regardless of grounding. (M3, M7)
8. `Proposal` is a discriminated union with a `QUERY` kind; `web/app/api/chat/route.ts` branches on query before `stageOperation` and dispatches to a new read registry in `web/lib/ops/query.ts` that has no commit, undo, or verdict surface; a named test asserts a QUERY never writes a row and never reaches `/api/ops/confirm`. (M4)
9. The roughly 15 owner questions ("cuanto vendi hoy", "que stock me queda", "que proveedores tengo", "que atiendo hoy", "que llegadas estan atrasadas", catalog, margins, cost scenarios) each return a rendered Spanish answer from an existing domain read function, calling the domain functions directly rather than the GET route handlers. (M4)
10. `web/app/api/chat/route.ts` accepts a bounded, role-tagged operator transcript; `web/lib/verdict.ts` grounds numerals against a server-authenticated record of the operator's own turns in the active flow only, never against assistant turns and never against a client-supplied transcript; a named test in `m7-injection.mts` asserts a forged operator turn in the request cannot launder an ungrounded amount onto the auto path. (M5)
11. A multi-turn flow completes: "vendi 40 stanleys" then "a que precio?" then "32" posts the sale with both numerals grounded to the operator's own turns; attribute expansion turns "medias azules y grises a 5" into two items. (M5)
12. New ops and parser intents for `recordProduction`, `createSupplier`, `recordCheckin`, and product non-price edit (name, sku, unit cost) are reachable from chat, each confirm-only. (M6)
13. An app-orchestrated guided flow lets the owner build a product's cost model by chatting: a controller inspects the ungrounded required fields and asks one question at a time, answers accumulate across turns, interdependencies (cost input before purchase before BOM line) resolve by server-side reads, partial states render as pendiente, and each of the eight costing and logistics writes commits as its own irreversible confirm step. The app computes derived USD from the operator's own FX inputs; the model never supplies the derived figure. (M7)
14. New aggregation reads answer monthly and date-range profit and revenue, expense by category and by period; any new aggregation preserves the CANCELACION negative-netting sign convention so the ledger still conserves; a named test asserts a cancelled expense nets correctly in a category and period total. (M8)
15. A stock adjustment to an absolute count ("en realidad tengo 12") is reachable as an ADJUSTMENT movement; a durable recent-committed-ops read (`pending_ops` where status is COMMITTED) loads on chat mount so Undo survives a page refresh. (M8)
16. `web/scripts/m7-injection.mts` and `web/scripts/m7-posture.mts` run green over compound, query, cancel, edit, and guided-cost flows; new cases prove no QUERY leaks cross-business rows, no resolver can be hijacked by operator text to target another entity, and the posture check is re-run after M6 and M7 grow the SYS prompt. (M9)

## Mockup

The user-facing chat surface was designed before implementation via a Phase 4.5 mockup deliberation with Kaze and Sally, on the existing Beans Command Center indigo identity. The frozen mockup lives at `./mockups/index.html` and is the visual contract any /develop run inherits.

- Screens covered: one chat surface with the QUERY answer, the compound create-then-act card, the disambiguation picker, the cancel card, the guided cost-flow card, and the settled receipt with Undo.
- State machine: empty (example chips), loading (inline shimmer), populated (mixed answer/create/cancel/cost cards), error (parse-fail, validation, no-permission, server-failure as calm notes).
- Three response shapes as the safety feature: answer (borderless, no button), create (neutral card, indigo Confirmar), cancel (amber, verb-bearing confirm, full consequence).
- Iterations: 1 (approved first look). See `./mockups/iterations.md`.
- Approved on: 2026-10-24.
- Design panelists: Kaze, Sally.

The atomic task list is pinned with T-000 (port the approved mockup into the chat surface); all states reachable, three response shapes, copy and density match the frozen mockup. It is autodev-labeled and ships first.

## Whole-problem surface

```yaml
surface:
  - id: s-01
    surface: "Ordered-steps Proposal contract where the step stays the unit of commit (one op_token, one verdict, one /confirm each, no cross-step transaction)"
  - id: s-02
    surface: "Compound create-then-act confirm card when a stock or sale hits product-not-found, with REGISTER_PRODUCT minting a name-only minimal product"
  - id: s-03
    surface: "Server-side reference resolution (descriptor to id) for sales, expenses, and stock movements, mirroring resolveActiveProduct; the model emits descriptors never ids"
  - id: s-04
    surface: "Chat disambiguation picker when a reference resolves to more than one candidate, each option carrying the server-resolved id"
  - id: s-05
    surface: "The six built-in correction and edit ops reachable by natural language (cancel sale/expense/stock, update price, deactivate product, register product), each confirm-only with full-consequence preview"
  - id: s-06
    surface: "QUERY read-only proposal kind dispatched before staging to a read registry with no commit, undo, or verdict surface"
  - id: s-07
    surface: "The ~15 owner reads wired to the read registry with Spanish NL dispatch, calling domain functions directly"
  - id: s-08
    surface: "Multi-turn context carried in the request with grounding bounded to a server-authenticated record of the operator's own turns in the active flow"
  - id: s-09
    surface: "Attribute expansion turning one multi-attribute utterance into multiple item steps"
  - id: s-10
    surface: "Orphan operational writes reachable from chat (production record, supplier create, supplier check-in, product non-price edit), all confirm-only"
  - id: s-11
    surface: "App-orchestrated guided cost-intake flow: a controller reads missing fields and asks one question at a time, honoring the cost-model dependency order and partial states"
  - id: s-12
    surface: "The eight cost-model and logistics writes registered as irreversible ops, with derived USD computed by the app from the operator's own FX inputs"
  - id: s-13
    surface: "New aggregation reads (monthly and date-range profit and revenue, expense by category and period) preserving the CANCELACION sign convention, plus stock adjustment to an absolute count"
  - id: s-14
    surface: "Durable recent-committed-ops list so Undo survives a page refresh"
  - id: s-15
    surface: "Registry-level permanent requires-human-review stamp on destructive and cost-model ops, independent of the dynamic verdict"
  - id: s-16
    surface: "Three distinct chat response shapes as a safety feature: answer (calm, no button), create (neutral card), undo-or-cancel (amber, deliberate)"
  - id: s-17
    surface: "Injection and posture corpus over the expanded surface: no cross-business read leak, no resolver hijack, no provenance laundering, posture re-proved after the SYS prompt grows"
```

## Open questions

1. The grounding substrate for multi-turn (M5). Winston's D-048 kept all history in the request with no server state and relied on assistant turns being non-grounding by construction. Tamir and Amelia converged that a client-supplied transcript lets a forged operator turn launder an ungrounded amount, which the assistant-turn exclusion does not defend against. Resolved toward the security lens as D-052: the request carries history for context and resume, but grounding runs only against a server-authenticated, nonce-bound, append-only record of the operator's own turns for the active flow. This is lighter than the dropped specs-001/002 session table (operator utterances for the active flow only, not a full conversation store) but is server state, which the 008 rebuild tried to avoid. Default if unrevisited: build D-052 as written. Right person: Dario, on whether the small grounding record is acceptable server state.
2. M7 cohort split boundary. Bob flagged M7 as too big for one cohort (eight interdependent writes plus a new guided-flow framework). Default: split M7a (framework plus cost-input, purchase, BOM line, packaging) and M7b (labor, shipping, customs, indirect pool). Right person: Bob or /develop at drain time.
3. How much of the cost model the owner realistically enters by voice versus a one-time assisted setup. Dario chose conversational entry (2026-10-24). If a real walk shows it is too heavy for pure chat, M7's guided flow is the place to add a compact multi-field card. Right person: Dario, after the mockup walk.

## Panelists who contributed

- Winston (Architect, BuildOS) — the five load-bearing decisions D-046 to D-051; step-as-commit-unit; the compound substrate is half-built in pending-ops.
- Amelia (Developer, BuildOS) — M1 is three files but not trivial (the error channel must become a structured payload and REGISTER_PRODUCT must mint a minimal product); M4 cannot reuse the GET handlers; M7 strictly depends on M5.
- Bob (Scrum Master, BuildOS) — the five-cohort sequencing; M4 has no dependency on M2 and pulls forward; M7 must split.
- Kaze (Creative Director) — the confirm button is overloaded to the point of turning the safety spine into theater; three distinct response shapes as a safety feature.
- Edut (Moral Conscience) — Legion Action Gate pass, conditional; destructive and cost ops stamped permanently human-review at the registry, not dynamically.
- Tamir (Rooted Shield, threat model) — the direct-id bypass and the provenance-laundering vector; the concrete M9 injection corpus; resolution must be server-side.
- Marcus (Financial Modeler) — the FX grounding gap (ground the operator's own inputs, let the app compute USD); M8 is real query work and must preserve the CANCELACION sign convention; the cost-model dependency order.
