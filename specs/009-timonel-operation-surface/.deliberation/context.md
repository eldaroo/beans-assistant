# Context packet — Spec 009: Timonel full operation surface

Run id: timonel-operation-surface-20261024-174517
Target repo: eldaroo/beans-assistant (target_kind = existing)
Base branch: claude/008-vercel-migration (the new Vercel+Neon app lives in `web/`; NOT origin/main, which is the old pre-rebuild Beans)
Worktree with the 008 code checked out: C:/Users/loko_/Documents/Projects/qie/clients/eldaroo/.worktrees/beans-native-chat (the Next.js app is the `web/` subdir)
architecture_author = true, mode = update, path = ARCHITECTURE.md at repo root, next decision ordinal = D-046
kaze_attach = true (user-facing chat surface)

Each panelist writes against THIS packet, in their own voice, in their own review file. The packet is pre-grounded: a 5-agent code audit already ran this session, so the built-vs-gap split below is verified against the live code. Do not re-derive it; build on it, and flag anything in it you find wrong.

---

## The raw idea (verbatim from Dario, via Quinn)

The owner logged into the live Beans app and hit a wall. He typed "me entraron 50 pulseras rojas" and Timonel answered product_not_found; he typed "dale, registralo" and Timonel answered "No pude interpretar eso como una operacion." He asked whether we need to give the model tools, or put a full agent (Lattice) in Nomad. A 3-agent investigation concluded: the problem is NOT missing model power, it is a missing APP-ORCHESTRATION layer. The decision (locked, do not reopen): keep the stateless, tools-off, propose-only parser as the spine; deliver "full power" as a UX feeling through app orchestration.

A second 2-agent audit then mapped the WHOLE operation surface of the platform. This spec connects that whole surface to the conversational assistant.

## Title

Timonel full operation surface — connect every business operation to the conversational assistant, inside the propose-only architecture.

## The architecture spine (HARD CONSTRAINT — do not reopen)

The parser (remote stateless Claude job on Nomad `beans-parse`, or the local deterministic fallback) ONLY turns text into a `Proposal {operationType, args}`. It holds no DB credential, has every built-in tool disabled, runs one turn, is bearer-gated, fails closed. The app re-derives the verdict from scratch (`web/lib/verdict.ts`) and is the ONLY thing that commits, via the non-model `POST /api/ops/confirm`. Proven by `web/scripts/m7-injection.mts` (no operator text or forged proposal field flips the server verdict; staging commits nothing) and `web/scripts/m7-posture.mts` (parser carries no DB cred, tools off, one turn, fails closed). Both MUST keep holding over the expanded surface.

Do NOT give the model tools or DB credentials. That was spec 007's native tool-use gateway (`mcp__beans__*`, `/run-agent`), retired at the spec-008 cutover for latency and injection reasons that still apply. "Full power" is a UX feeling (the assistant does what I say in one conversation), delivered by compound proposals + multi-turn context + read-dispatch + reference resolution, leaving the model powerless on purpose.

### Arch-doc vs code divergence (important for Winston)

ARCHITECTURE.md decisions D-034 through D-045 (spec 007) describe a native tool-use loop with MCP tools and a boot tool-posture self-check. Spec 008 (the Vercel+Neon rebuild, now live at beans-rouge.vercel.app) RETIRED that loop and replaced it with the stateless propose-only parser. The arch doc may not carry a spec-008 addendum recording this. Ground every decision against the LIVE 008-branch code in `web/`, not against D-034 to D-045. Winston's mode=update addendum starts at D-046 and should note that spec 008's propose-only rebuild is the live brain that spec 009 extends.

## Built vs gap — verified against the live 008-branch code (5-agent audit)

The UI is 100% READ-ONLY: all 9 module pages under `web/app/(app)/*/page.tsx` are tables with zero action buttons. **Timonel chat is the SOLE write and correct lever in the whole app.** This raises the stakes: everything the owner needs to DO must go through the chat.

Coverage today:
- WRITES: 3 of 21 domain write functions reachable (REGISTER_SALE, REGISTER_EXPENSE, ADD_STOCK). The other 18 are unreachable from chat.
- READS: 1 of ~16 natural owner questions answerable (only cost-scenario). ~15 have a working domain fn + GET route but the chat route never calls them.
- CORRECTIONS: 0 of 6. CANCEL_SALE, CANCEL_EXPENSE, CANCEL_STOCK, UPDATE_PRICE, DEACTIVATE_PRODUCT, REGISTER_PRODUCT all exist in `web/lib/ops/registry.ts` with working commit + undo + verdict (all forced confirm-only, irreversible), but NO parser emits them.

Three tiers of effort:
- TIER A (cheap, logic exists): 6 registry-complete ops just need a parser intent; ~15 reads just need dispatch. The two keystones below unlock most of this.
- TIER B (medium): restore multi-turn memory (specs 001/002 were dropped in the 008 rebuild).
- TIER C (new build): 13 orphan writes have NO op and NO route — costing/logistics data-entry x8 (recordCostInput, recordInputPurchase, recordBomLine, recordPackagingCost, recordLaborBatch, recordShippingLane, recordCustomsDuty, recordIndirectPool; the cost model is read-only-feedable, populated only by DB seed today), production x1 (recordProduction), suppliers x2 (createSupplier, recordCheckin), products non-price fields (updateProduct supports name/sku/unitCostCents, only UPDATE_PRICE exposes price).

### Two keystones that unlock most of the surface

1. Reference resolution: a read that turns "la ultima venta" / "la venta de Juan" / "las medias" / "el gasto de luz" into a numeric id. Cancels and edits all need an id and there is no resolver on a read path today. Plus a chat disambiguation picker ("cual? 1) ... 2) ...") when more than one match. `resolveActiveProduct` exists for writes but is not invoked on a price-change or read path, and ambiguity (>1 match) has no picker.
2. Read-dispatch: route a natural-language question to an existing domain read fn. New proposal kind QUERY = read-only, no verdict, no confirm. The data and GET routes already exist for ~15 questions; the chat route just never calls them.

Genuinely MISSING data work (not just wiring): monthly/date-range profit and revenue (current views are all-time single-row), expense-by-category and expense-by-period aggregation, stock ADJUSTMENT set-to-absolute ("en realidad tengo 12"; domain supports ADJUSTMENT movementType, no intent reaches it), and a durable recent-committed-ops list so Undo survives a page refresh (today the op_token lives only in React state in `web/app/(app)/_components/chat.tsx`).

## The milestone plan (integral arc; group into cohorts of <=10; propose-only throughout)

- M1 Compound create+act: ADD_STOCK or a sale that hits product_not_found offers a 2-step confirm-card REGISTER_PRODUCT then ADD_STOCK. ~3 files, zero parser/verdict change. The screenshot fix.
- M2 Reference resolution + chat disambiguation picker (KEYSTONE 1).
- M3 Wire the 6 correction/edit ops to NL parser intents, riding M2. Commit layer + verdict already exist. "cancela la venta 42", "cambia el precio de las medias a 350", "da de baja los termos".
- M4 Read-dispatch QUERY type (KEYSTONE 2). "cuanto vendi hoy", "que stock me queda", "que proveedores tengo", "que atiendo hoy", catalog, margins, cost scenarios.
- M5 Multi-turn context + resume memory (restores specs 001 + 002 ON TOP of the stateless parser). History travels in the request; server grounds numerals only against the operator's own turns in the active flow. "vendi 40 stanleys" then "a que precio?" then "32" completes; carry a referent across turns. Also attribute expansion ("medias azules y grises a 5" -> 2 items).
- M6 Orphan operational writes (new ops + parser intents): production (recordProduction), suppliers (createSupplier, recordCheckin), product non-price edits.
- M7 Cost-model data entry, CONVERSATIONAL GUIDED FLOWS. Dario's decision (2026-10-24): the owner enters the cost model by chatting with Timonel, NOT an admin form. The 8 costing/logistics writes with no op/route today; structured, interdependent data; design multi-turn guided flows (lean on M5). This is what makes the costing dashboard actually feed-able. Heaviest milestone.
- M8 New aggregation reads + durable undo: monthly/date-range profit and revenue, expense-by-category/period, stock ADJUSTMENT set-to-absolute, durable recent-ops list so Undo survives refresh.
- M9 Injection hardening over the expanded surface: run the m7-injection corpus over compound/query/cancel/edit/guided-cost flows; prove no read leaks cross-business data, no cancel/edit/cost-write auto-commits without the app's verdict + /confirm, reference resolution cannot be hijacked by operator text. Extends spec 008 AC7.

Everything additive to the propose-only spine; commit always stays the non-model /confirm route.

## Key files (all under the 008 worktree `web/`)

- Parser: `web/lib/parse/{types,fallback,client}.ts` + `deploy/beans-parse.nomad.hcl` (SYS prompt; one level up from web/)
- Ops: `web/lib/ops/{registry,stage}.ts`, `web/lib/pending-ops.ts`, `web/lib/verdict.ts`
- Routes: `web/app/api/chat/route.ts`, `web/app/api/ops/{stage,confirm,undo}/route.ts`, GET routes `web/app/api/{hoy,products,stock,sales,expenses,costing,production,suppliers,logistics,analytics}/route.ts`
- Domains: `web/lib/domains/*.ts` (21 write fns + reads)
- Chat UI: `web/app/(app)/_components/chat.tsx`; module pages `web/app/(app)/*/page.tsx`
- Proofs: `web/scripts/m7-injection.mts`, `web/scripts/m7-posture.mts`, `web/scripts/m7-parity.mts`
- Dropped capability specs: `specs/001-timonel-conversational-memory`, `specs/002-timonel-pending-operations`
- Retirement rationale: `specs/007-native-tool-use-chat`, `specs/008-vercel-neon-migration` (AC7); arch D-034..D-045

## What each panelist writes

One review file at `_qie/specs/_panel-runs/timonel-operation-surface-20261024-174517/reviews/<panelist>-review.md`. Answer the six prompts:
1. What problem is this actually solving?
2. What is the smallest first version that proves the idea?
3. What 3 risks would kill this if ignored?
4. What does success look like at 90 days?
5. What atomic tasks does this break into? (list 5-15, each <=1 day; tag each with a milestone M1..M9)
6. What is the one thing only your faculty would have noticed?

Hard limit 600 words. Ground your review in the live 008-branch code, not the arch doc's retired spec-007 decisions.
