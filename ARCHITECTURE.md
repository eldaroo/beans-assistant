---
name: timonel-architecture
last_spec: native-tool-use-chat
created: 2026-06-11
last_updated: 2026-10-19
mode: update
author: Winston (BuildOS Architect, architecture-author role)
---

# Architecture: Timonel interpretation and orchestration

> The decision log for the Timonel pipeline. The spec is the what and why; this file is why this shape, not the others.

## System shape

Timonel is a LangGraph pipeline over a shared TypedDict state. Each turn flows decomposer to router to one of two arms (read, or resolver then write then optional read), then final_answer, with a sub-input loop for multi-intent turns. Today the pipeline can split a multi-action message and classify each action, but it has no step that turns a base noun plus a coordinated attribute list plus a shared modifier into a concrete set of products. This spec adds exactly one new module, a deterministic expansion node between router and resolver, and tightens two existing contracts (SKU generation in resolver, batch create in database). Every other boundary is preserved.

```
decomposer -> router -> [ read
                        | expander -> resolver -> write -> read? ]
                        -> final_answer -> (advance sub-input | END)
```

Modules in this system:

| Name | Responsibility | Owns |
|------|----------------|------|
| decomposer | split multi-intent turn into sub-inputs | sub_input_queue, cursor |
| router | classify intent and operation, extract items[] | intent, operation_type, normalized_entities |
| expander (new) | fan out base noun x attribute list, distribute shared price | the expanded flat items[] |
| resolver | bind product refs to ids, validate, generate SKUs | normalized product_id, SKU, missing_fields |
| write_agent | execute DB ops, build Spanish summary | operation_result |
| database | atomic-or-partial batch helpers | committed rows |
| graph | wiring, final_answer, missing-field translation | final_answer |

## Decision log

### D-001: Attribute expansion lives in a dedicated node between router and resolver

- **Chosen.** A new deterministic node `expander`, REGISTER_PRODUCT only, reads router items[] and emits a flat expanded items[] before the resolver runs.
- **Alternatives considered.** (a) decomposer splits the phrase into sub-inputs; (b) router LLM emits a fully expanded items[]; (d) resolver expands.
- **Why this won.** Expansion is a data-shape fan-out, not interpretation and not reference binding. It has one responsibility and no side effects, so it is independently testable. It is also the only place that can hand the SKU generator the full sibling set before any row is written, which is the precise condition the collision needs.
- **Why the alternatives lost.** (a) The decomposer works on raw text before classification, so it cannot know an action is REGISTER_PRODUCT or which tokens are a price versus an attribute; distributing a shared price across siblings would mean re-implementing extraction. (b) The router prompt is already long and exampled; folding combinatorics into the classify-and-extract call makes one fragile call own two jobs, and a drift in either is undiagnosable. (d) The resolver binds refs to ids one item at a time; expanding there means siblings are computed mid-resolution and the SKU generator still lacks the full set unless we reorder the resolver internally, which is a bigger change than a clean node.
- **Implications.** Router contract gets simpler, not larger: it emits the base noun, the attribute list, and the shared modifiers, and stops there. The graph gains one conditional edge. Read and non-product write paths bypass the node entirely.
- **Panel source.** Winston. Dissent logged: Lattice, Amelia and Bob favored the decomposer placement (one fewer node, no risk of fighting the router AMBIGUOUS path). Tracked as spec Open Question OQ1, resolved at /develop M1.

### D-002: Expansion is deterministic, LLM only as a fallback

- **Chosen.** Color lists and size lists are expanded by a pure function. The LLM is used only when the router flags the attribute phrasing as genuinely ambiguous.
- **Alternatives considered.** Always-LLM expansion; always-deterministic with hard failure on unknown grammar.
- **Why this won.** The grammar that matters here is regular: a noun followed by a coordinated list joined by commas and "y", with one trailing price. Deterministic code is testable, free, and cannot hallucinate a product.
- **Why the alternatives lost.** Always-LLM adds cost and a hallucination surface to the most common case. Hard-failing on unknown grammar regresses turns the system handles today.
- **Implications.** The node fails open: anything it does not recognize passes through unchanged to the resolver as the existing single-item path. No turn gets worse than today.
- **Panel source.** Winston, grounded in the cheap-LLM cost constraint.

### D-003: Shared modifier (price) distributes at expansion time

- **Chosen.** The trailing shared price is attached to every expanded sibling inside the expander, in cents, before resolution.
- **Alternatives considered.** Distribute in the resolver during validation; leave price on a parent object and have write_agent fan it out.
- **Why this won.** The expander is the one node that holds both the sibling set and the shared modifier in the same scope. Distributing there means every downstream node sees uniform, complete items and never has to reason about a parent-child price relationship.
- **Why the alternatives lost.** Resolver distribution couples validation to expansion semantics. A parent-price object leaks a second shape into write_agent and the summary builder.
- **Implications.** Price stays nullable: an item with no shared price expands to siblings each with unit_price None, and the existing precio-pendiente path handles them.
- **Panel source.** Winston.

### D-004: SKU uniqueness is computed within the batch, with token retention

- **Chosen.** `generate_sku_from_name` dedupes against in-flight siblings AND committed rows, and the generator retains discriminating tokens (color, size) rather than dropping single-letter size tokens.
- **Alternatives considered.** Keep DB-only dedup and let the constraint catch collisions; push uniqueness entirely into the DB with a retry loop.
- **Why this won.** The collision in the screenshot is three siblings sharing a base SKU because none exist in the DB yet. Uniqueness must see the batch as a set. Retaining size and color tokens is what makes the base distinct in the first place, so dedup becomes the rare fallback rather than the rule.
- **Why the alternatives lost.** DB-only dedup is exactly the current bug. A DB retry loop hides a generator that produces colliding names and adds write amplification.
- **Implications.** The generator signature gains the in-flight sibling set. Size tokens that are single letters are no longer skipped when they are the discriminator.
- **Panel source.** Winston, Amelia, Lattice.

### D-005: Batch create degrades to partial success

- **Chosen.** `register_products_batch` lands every valid item and returns a per-item result list. It no longer rolls back the whole turn on one bad row.
- **Alternatives considered.** Keep atomic all-or-nothing; atomic with a pre-flight validation pass that rejects the whole batch on any invalid item.
- **Why this won.** "Cargue dos de tres, falta el precio de Medias Grises" is honest and useful. All-or-nothing tells the owner nothing landed when two were valid, which is the screenshot's second failure dressed differently.
- **Why the alternatives lost.** Atomic is the current behavior and it punishes the owner for a single missing field. A pre-flight reject still loses the valid work.
- **Implications.** write_agent and final_answer must aggregate a per-item outcome list, not a single success or error. This is the larger downstream change and ships behind goldens in M2.
- **Panel source.** Winston, Mar'ah.

### D-006: Missing-field messages name product and field, never indices

- **Chosen.** The resolver attaches structured per-item missing fields carrying the product name and the human field name; graph and write_agent translate from that structure, never from `items[i].field`.
- **Alternatives considered.** Extend the flat translation table to cover indexed names; suppress the index and emit a generic count.
- **Why this won.** "ese dato" is the flat table hitting an indexed key it cannot translate. Carrying the name and field in the structure removes the fallback path entirely and produces "Medias Grises: falta el precio".
- **Why the alternatives lost.** Translating indexed keys is brittle and grows with every operation. A generic count tells the owner nothing actionable.
- **Implications.** missing_fields stops being a list of strings for the multi-product path and becomes a list of {product, field}. Single-item paths keep their flat shape; the translator handles both. The two duplicated translation tables (write_agent.py, graph.py) collapse into one `agents/field_labels.py`.
- **Panel source.** Winston, Amelia, Mar'ah.

### D-007: The resume path is deterministic code, not a second router call

- **Chosen.** A `resume_gate` node runs before the decomposer and router. When a pending operation matches the reply, it rebuilds the stored entities in code and routes directly into the resolver and write arm.
- **Alternatives considered.** Enrich the router prompt via `pending_entities` so the LLM re-extracts; or re-ask the router constrained to the pending operation.
- **Why this won.** Correctness of a completed financial write must be deterministic. The router is Gemini flash, the named unreliable point, and a wrong completion is a wrong ledger row.
- **Why the alternatives lost.** The first is the current bug: the LLM dropped the product across two turns with context present. The second puts correctness behind a probabilistic call.
- **Implications.** A new entry node sits ahead of the decomposer; the router's "Example 3b" stops being load-bearing for the resume path.
- **Panel source.** Winston, Mary, Amelia.

### D-008: The pending record lives in the per-phone in-process store, not the tenant DB

- **Chosen.** Persist `PendingOperation` alongside the existing `_history_by_key` class state in `ChatService`, keyed by phone, expired by a TTL.
- **Alternatives considered.** A row in the per-tenant SQLite or Postgres DB; a new dedicated store.
- **Why this won.** A pending operation is conversational working state with the history buffer's lifetime and key, and must not survive a restart: a half-finished sale resumed after a deploy is a hazard.
- **Why the alternatives lost.** The tenant DB holds committed facts; an uncommitted intent there invites a reader treating it as real, and restart-survival is the failure we reject. A new store duplicates the buffer's TTL and keying.
- **Implications.** The single-worker assumption is inherited and acceptable; when spec #63 makes history durable, the record rides the same migration.
- **Panel source.** Winston.

### D-009: A new `PendingOperation` type, not the existing `pending_entities` seam

- **Chosen.** A `PendingOperation` carrying `operation_type`, the resolved entities to complete (`product_id`, `quantity`), `missing_fields`, `op_token`, `created_at`. The existing `pending_entities` stays a router-prompt hint, untouched.
- **Alternatives considered.** Extend `pending_entities` to carry resolved ids and drive resume off it.
- **Why this won.** `pending_entities` is a `{name, missing_fields}` prompt hint with no resolved `product_id`, no quantity, no token, and it only populates when `missing_fields` is non-empty (the sale-needs-price branch sets none). Resume needs resolved state.
- **Why the alternatives lost.** One shape spanning an LLM-hint role and a determinism-critical role makes each constrain the other.
- **Implications.** `write_agent`'s sale-price block, returning no pending data today, now emits a `PendingOperation` with `product_id` and `quantity` in hand.
- **Panel source.** Winston, Amelia.

### D-010: Completion is idempotent via an op_token recorded at commit

- **Chosen.** Each `PendingOperation` is stamped with an `op_token` at creation. Resume clears the record before commit; the committed sale records the token; a second resume of the same token is refused.
- **Alternatives considered.** Trust the single-worker model and skip the token; dedupe by a (product, quantity, minute) heuristic.
- **Why this won.** Never double-record a sale is the hard constraint. A retried turn, double-tapped send, or graph retry must commit once; only a token survives all.
- **Why the alternatives lost.** In-process storage does not stop a retried turn resuming a still-present record. A heuristic can suppress a legitimately repeated sale.
- **Implications.** Resume clears-then-commits: a crash mid-commit loses the resume rather than risking a double.
- **Panel source.** Winston, Mar'ah.

### D-011: The pending record expires by TTL and is cleared on cancel or change of mind

- **Chosen.** A record older than the configured TTL never resumes. A cancel, or any reply the gate cannot match to the missing field, clears it (or leaves it to re-ask) and falls through to the cold path.
- **Alternatives considered.** Keep the record until explicitly resumed; resume on any numeric reply.
- **Why this won.** Handling cancel and change-of-mind mid-detour is in scope. A pause is not a lock; a stale resume is a wrong ledger row, so expiry and cancel-clears default safe.
- **Why the alternatives lost.** An indefinitely held record resumes a phantom an hour later; resuming on any number guesses, which the constraint forbids.
- **Implications.** The match fills only when the reply unambiguously is the missing field; otherwise the gate re-asks or clears.
- **Panel source.** Winston, Mar'ah, Edut.

### D-012: Resume serves only fully-resolved paused operations in v1

- **Chosen.** Resume fires only when the paused operation holds every entity except the one missing field. Operations needing fresh disambiguation cold-classify.
- **Alternatives considered.** A general resume that re-resolves arbitrary missing entities across turns.
- **Why this won.** A resolved-except-one-field pause is a closed, testable transition. Re-resolving an arbitrary entity reintroduces the LLM, which D-007 forbids.
- **Why the alternatives lost.** A general re-resolver is a larger surface that puts the unreliable path back on the money line.
- **Implications.** v1 covers sale-needs-price and (M2) one more single-missing-field pause; broader resume is a later spec.
- **Panel source.** Winston.

## Costing domain addendum (spec 003, production-landed-cost-engine)

A new per-tenant costing domain hangs off the existing `products` table and computes one derived fact: landed cost per bracelet type, per country, in USD, with a completeness state. Raw facts are entered once each; landed cost is always computed, never hand-entered. Suppliers become scoped users of the same tenant via a new membership layer. Check-ins reuse Baileys and Timonel. The UI makes costing the home surface without deleting sales, stock, or expenses.

| Module | Owns |
|--------|------|
| costing schema (new per-tenant tables) | raw cost facts |
| suppliers repository and api | supplier rows |
| costing_service | the derived snapshot and allocation |
| tenant_members (public) | who may reach a tenant |
| checkin scheduler | send cadence and log |
| costing home | costing routes and templates |

### D-013: `products` is the bracelet-type anchor; costing in new tables

- **Chosen.** One bracelet type stays one `products` row. New costing tables, keyed by product_id or country: suppliers, cost_inputs, input_purchases, bom_lines, labor_costs, packaging_costs, shipping_lanes, customs_duties, indirect_costs, landed_cost_snapshots.
- **Alternatives.** (a) a separate `bracelet_types` table; (b) costing columns onto `products`.
- **Why won.** `products` already carries SKU and is referenced by sales, stock, and sale_items. It is the one existing identity for a bracelet type.
- **Why lost.** (a) forks identity into two sources of truth. (b) costing is many rows per product per country, not flat columns on one row.
- **Implications.** `create_tenant_schema` gains the tables plus a backfill. Landed cost is a derived snapshot, not a `unit_cost_cents` write.
- **Panel source.** Winston.

### D-014: Input purchases store original currency, FX rate, and USD; append-only

- **Chosen.** `input_purchases` stores original_currency, original_amount_cents, fx_rate, usd_amount_cents, purchased_at. The rate is hand-entered in M1. A correction is a new row, never an in-place edit.
- **Alternatives.** (a) USD only; (b) original plus a fetched live rate.
- **Why won.** The triplet is a full audit trail: a disputed cost is re-checkable and a wrong rate is visible.
- **Why lost.** (a) hides a wrong rate. (b) a live rate drifts from the rate actually paid; a fetched rate is a later default, not the stored truth.
- **Implications.** A USD normalization helper sits beside the repository; a rate edit means a new row and snapshot.
- **Panel source.** Winston, with Amelia on the blind existing `currency` column.

### D-015: Indirect allocates per unit produced, per country, per month

- **Chosen.** Indirect per bracelet equals total indirect cost for a country in a month, divided by units produced there that month. Display stands and overhead use this basis.
- **Alternatives.** (a) per revenue; (b) per batch.
- **Why won.** Per-unit-produced is the honest denominator and does not depend on the price being computed.
- **Why lost.** (a) is circular: price is the output, so allocating by revenue defines the answer in terms of itself. (b) batches are uneven; display stands are not per-batch.
- **Implications.** `costing_service` needs a per-country per-month production count; a zero-production month renders indirect PENDING.
- **Panel source.** Winston. Marcus favored a rolling trailing window over a calendar month; the window choice is OQ1 (A-Q5), resolved at build.

### D-016: The snapshot carries a completeness state, never a false total

- **Chosen.** A snapshot holds each component (materials, labor, packaging, shipping, customs, indirect) with a filled or pending status and a completeness enum. The partial total renders beside the list of pending components.
- **Alternatives.** (a) block computation until complete; (b) treat pending as zero.
- **Why won.** The CEO said some numbers are not known yet. Gaps are the normal state, and a visible gap is the prompt to fill it.
- **Why lost.** (a) no number ever renders. (b) silently understates cost and the CEO prices on a lie.
- **Implications.** Every costing surface reads the completeness state; a complete total is a distinct, earned state.
- **Panel source.** Winston, Mar'ah.

### D-017: Supplier-as-user is a membership model, not a role flag

- **Chosen.** Add `public.tenant_members` mapping an app_user to a tenant phone with a role (owner or supplier) and an optional supplier_id. `require_tenant_match` resolves a member to the tenant. Supplier queries filter by supplier_id; cost, price, and margin are owner-only.
- **Alternatives.** (a) a tenant schema per supplier; (b) a role column on app_users alone.
- **Why won.** One tenant with several scoped users is the requirement: the CEO sees the whole model, each supplier only their own rows.
- **Why lost.** (a) fragments the data so the CEO cannot consolidate. (b) the phone-keyed guard cannot express many-users-one-tenant, so suppliers cannot log in or they over-read.
- **Implications.** Touches the auth kernel, so not autodev. The within-tenant scope is a server-side read filter, never a template. Kaze reinforces: the supplier and CEO surfaces are two separate rooms, never one screen hiding margins behind conditionals.
- **Panel source.** Winston, with Edut and Mar'ah on consent and harm, Kaze on surface separation.

### D-018: Check-ins reuse Baileys outbound and Timonel

- **Chosen.** A periodic scheduler calls the existing Baileys outbound to send a check-in. Replies route back through Timonel with a new PRODUCTION_UPDATE intent. A non-parsing reply is stored verbatim as a note to the CEO; it never force-writes and is never dropped.
- **Alternatives.** (a) a second bot or channel; (b) a parser separate from Timonel.
- **Why won.** The channel and the interpreter already exist; a check-in is one more intent, not one more system.
- **Why lost.** (a) the directive forbids a second channel. (b) duplicates Timonel and splits the truth of how a message is read.
- **Implications.** The scheduler owns cadence and a send log; the sender identifies the business truthfully. External send ships behind the sacred gate (named-human-signoff, Dario, Re'i co-attestation).
- **Panel source.** Winston, with Mar'ah and Edut.

### D-019: The UI reframe is additive; nothing is deleted

- **Chosen.** A new costing home route and template become the default landing surface; nav reorders so sales, stock, and expenses sit as secondary sections. No existing route or template is removed.
- **Alternatives.** rebuild the dashboard around costing.
- **Why won.** "Reencuadrar, no borrar." Reordering preserves working code.
- **Why lost.** A rebuild tears out proven layout code, which the directive forbids.
- **Panel source.** Winston, grounding Dario.

## Control Center shell addendum (spec 003 reframe, 2026-10-13)

Dario reframed the spec mid-run: the target is the Beans Control Center, a command-center platform that nucleates the whole business, with costing as one module. The platform becomes a shell: a status home rendering one tile per registered module plus an attention strip. The shell owns no domain logic, only a module registry and two provider contracts. On FastAPI and Jinja a module is a server-side descriptor over the existing api, service, and repository triple, not a frontend component.

| Module | Route | Headline number | Attention rule | Status |
|--------|-------|-----------------|----------------|--------|
| Home / Panel | `/` | aggregates all | aggregates all | new shell |
| Producción | `/produccion` | units this week | arrival cadence overdue | new |
| Proveedores | `/proveedores` | active suppliers | overdue check-in | new |
| Costos y margen | `/costos` | margin per country | pending cost component | new, reuses D-013 to D-016 |
| Inventario / Stock | `/stock` | low-stock count | low coffee stock | existing, plus providers |
| Ventas | `/sales` | sales this week | none in M1 | existing, plus providers |
| Caja / Gastos | `/expenses` | cash balance | negative cash signal | existing, plus providers |
| Logística | `/logistica` | open lanes | pending customs line | new |
| Asistente (Timonel) | `/chat` | not a tile | n/a | existing, plus scenario read-path |

### D-020: The home is a module registry plus a provider protocol

- **Chosen.** A static registry of module descriptors in `backend/modules/registry.py`. Each carries id, Spanish label, route prefix, and two callables: `headline(tenant, user)` and `attention(tenant, user)`. The status home iterates the registry, rendering one tile per descriptor plus the attention strip.
- **Alternatives.** (a) a home template that hard-codes each tile; (b) a DB-driven registry.
- **Why won.** One headline per module aggregates through a uniform contract, so adding a module is a descriptor plus two methods, never a home edit. It fits the repo: each module already owns an api, service, and repository.
- **Why lost.** (a) couples the home to every module. (b) modules are code, not data; the indirection has no caller yet.
- **Implications.** A `Headline` dataclass (value, unit, Spanish label, status, href) and an `AttentionItem` dataclass. Providers are bounded and fail to a degraded tile, never raising into the page, per the repo's fail-open convention.
- **Panel source.** Winston.

### D-021: Attention rules live in the module that owns the data, computed on read

- **Chosen.** Each module's `attention()` provider produces its own items (low stock, pending cost component, overdue supplier check-in, negative cash). `backend/services/attention_service.py` aggregates across the registry, sorts by severity, and caps the strip.
- **Alternatives.** (a) a central rules engine; (b) materialized attention rows.
- **Why won.** The module owns the data and the threshold meaning, so the rule belongs with it. A central engine would reach into every module's internals, the coupling D-020 forbids.
- **Why lost.** (a) centralizes knowledge the module owns. (b) adds a write path and staleness with no cost reason yet.
- **Implications.** An `AttentionItem` carries severity, module id, Spanish message, href, and a dedupe key; the strip orders by severity so it is not a second to-do list.
- **Panel source.** Winston, with Kaze on the strip not becoming noise, and Compass on signals codifying the CEO's existing rhythm.

### D-022: Costing scenarios are a read-only recompute the assistant runs (refines D-013 to D-016)

- **Chosen.** The stored `landed_cost_snapshots` are the source of truth and always shown. A pure `costing_service.recompute(snapshot, overrides)` computes a hypothetical in memory. Timonel gains one read-only COST_SCENARIO path that loads a snapshot, applies an override, and returns the recomputed number, never writing.
- **Alternatives.** (a) a heavy scenario UI; (b) a scenario that writes a draft snapshot.
- **Why won.** The fact lives in the platform; a what-if is a conversation Timonel already interprets. One formula serves both via `recompute`.
- **Why lost.** (a) builds a second costing surface for a question the chat answers. (b) a written draft pollutes the audit trail D-014 protects.
- **Implications.** `recompute` is the pure core the stored build also calls; the scenario path never persists. It adds a read-path over D-013 to D-016, not a change.
- **Panel source.** Winston, grounding Dario's second decision.

### D-023: The existing surfaces become first-class modules under the status home (refines D-019)

- **Chosen.** The default landing becomes the status home, not the costing home. Sales, stock, and expenses register as modules through D-020's registry, each exposing a headline and an attention provider; Producción, Proveedores, Costos, and Logística register the same way. Nothing is deleted; existing routes stay and gain a descriptor.
- **Alternatives.** keep D-019's costing-home-as-default.
- **Why won.** The reframe makes costing one module among seven, so no single module can be the home; the status home is the nucleus and every surface plugs in the same way.
- **Why lost.** A costing-home default re-centers the platform on one module.
- **Implications.** D-019's additive, delete-nothing principle stands. Only its clause "the default landing route is the costing home" becomes "the default landing is the status home; costing is one module".
- **Panel source.** Winston, grounding Dario.

## Control Center unification addendum (spec 004, 2026-10-14)

Dario made the Control Center the single owner-facing product. All CRUD moves off the legacy `/tenants/{phone}` page onto dedicated Control Center pages; legacy stays live, Admin-only, a fallback. These decisions govern how one design system and real write paths arrive without regressing the deployed home. They build on D-020 (registry plus provider protocol) and D-023 (existing surfaces as modules).

### D-024: One owner-facing base, extracted from the home; legacy base untouched; extraction is foundational

- **Chosen.** Extract a shared Jinja base `cc_base.html` from the current `control_center.html`, keeping its current modern Control Center design (indigo/Inter): shell structure, held nav, theme toggle, chat slot, and the existing token set. The home and every module page, read-only and new CRUD, extend it. Legacy `base.html` (coffee) is left exactly as is under Admin; the four coffee-styled read-only pages migrate onto the modern base. The extraction is the first cohort, before any new CRUD page. Note: Kaze (panel) recommended re-theming to coffee/cream since the business sells beans; Dario overruled and chose to keep the modern Control Center design, so the unified brand is the current modern look, not coffee.
- **Alternatives.** (a) A shared CSS or partial include across the standalone pages. (b) Leave pages standalone, theme-match by hand. (c) Migrate the legacy page onto the new base too.
- **Why this won.** Duplication across standalone documents is the debt; one base is the single place brand and nav change. Extracting from the already-shipped home re-bases it to a visually equal surface, preserved by construction and proven by the pixel self-regression gate (home as golden). First means each new page is born extending the base, written once.
- **Why the alternatives lost.** (a) A CSS include still leaves each page re-declaring doctype, head, nav, and theme, so nav drift persists. (b) Hand theme-matching is the status quo that produced the mixed surfaces. (c) Touching the legacy base risks the Admin fallback for zero owner gain.
- **Implications.** Two bases: `cc_base.html` (owner) and legacy `base.html` (Admin). The four existing read-only pages migrate in a styling-only cohort right after extraction. Building the base last (the naive M6) rewrites all four CRUD pages twice; this reorders design to the front.
- **Panel source.** Winston, with Bob on shell-first sequencing and Kaze on one brand, one nav; the brand choice (modern over coffee) is Dario's, overruling Kaze's coffee recommendation.

### D-025: CRUD pages are Alpine over the existing JSON endpoints; three read layers stay distinct

- **Chosen.** Each new page server-renders its initial read through the route `_build_view` (fast paint, tenant-scoped, `no-store`, fail-open) and hydrates one Alpine factory per page, mirroring the legacy `tenantDashboard`, that owns every mutation by calling the existing `/api/tenants/{phone}/...` endpoints then refetching. Three read surfaces keep separate jobs: provider `snapshot()` is the home tile number, route `_build_view` is the page initial render, `/api` endpoints are the Alpine CRUD path.
- **Alternatives.** (a) A client framework (React/SPA). (b) Server-side form posts with full reloads. (c) Fold page detail into the provider snapshot so tile and page share one fetch.
- **Why this won.** Alpine is already loaded and the legacy page already writes through this exact factory against these exact endpoints, so no new toolchain and the reuse constraint is honored by construction. The three-layer split keeps each path at its own cost and failure mode.
- **Why the alternatives lost.** (a) A framework adds a bundler and breaks D-020's server-rendered-descriptor convention. (b) Full reloads lose the inline stock-adjust interaction and fight the no-store model. (c) A shared fetch makes the home pay the page's full query, the regression D-027 guards.
- **Implications.** One Alpine factory per page template. Endpoints are never rewritten. The JS methods port verbatim but every Tailwind class and `--color-*` token re-expresses into the shared base vocabulary; the signed-delta stock conversion (`newQty - currentQty`) must survive the port. The two legacy gaps (unwired record-sale, alert-stub view-detail) are built on the new Ventas page against the present `POST /sales` and `GET /sales/{id}`; record-sale is a build, not a port.
- **Panel source.** Winston, with Amelia on reusing the endpoint contracts verbatim and the port traps.

### D-026: Routing stays registry-driven; productos is a new descriptor; tile repoints are registry edits

- **Chosen.** Every new or repointed surface is a change to `backend/modules/registry.py` plus a route, never a home-template edit (preserves D-020 and the Control Center AC1). `href_for` already treats a `/`-prefixed route as absolute, so repointing a bounced tile is a one-line change from `?tab=x` to `/{module}/{phone}`. `productos` is a new descriptor. The Resultado-to-expenses mislabel and the `?tab=expenses` base pointer are fixed when the caja/Resultado tile repoints.
- **Alternatives.** (a) Hard-code the new tiles and routes in the home template. (b) Keep a query-param tab router for the new pages.
- **Why this won.** The registry is already the single source of module truth; repointing through it keeps the home untouched and the invariant intact. Dedicated `/{module}/{phone}` routes replace the `?tab=` bounce to legacy.
- **Why the alternatives lost.** (a) Couples the home to every module, the coupling D-020 forbids. (b) The tab router is the mechanism that bounces to legacy; keeping it reintroduces the problem.
- **Implications.** Five registry touches: one add (productos), three repoints (stock, ventas, caja/Resultado), one label fix. No home-template edit.
- **Panel source.** Winston.

### D-027: Provider snapshots stay one bounded query; productos is the eighth concurrent snapshot

- **Chosen.** The productos provider does one bounded query (active product count) and fails open to a degraded tile, per D-020 and D-021. Page detail lives only in the route `_build_view`, never in the snapshot. New CRUD pages are client-fetch so they stay off the shared snapshot pool.
- **Alternatives.** (a) A richer productos snapshot feeding the tile. (b) Raise `SNAPSHOT_TIMEOUT_S` again.
- **Why this won.** The fan-out is concurrent, so one more bounded query does not serialize, but it is one more connection on the shared pool under the 10s deadline and the live latency. One count bounds the home's growth to one cheap query per module and protects the 0.9s render.
- **Why the alternatives lost.** (a) A richer snapshot makes the home pay page-weight for a tile. (b) Raising the timeout hides pool saturation and degrades felt speed.
- **Implications.** Productos is the eighth concurrent snapshot. Before it ships, confirm the pool serves eight concurrent bounded queries within the deadline at live latency; if it saturates, that fan-out is what #138 must fix (a combined per-module aggregate, per A-Q9), not a reason to inflate any snapshot.
- **Panel source.** Winston, grounded in the #138 perf debt.

### D-028: Timonel is embedded once in the shared base, not per page

- **Chosen.** The chat widget (`chat_widget.js` factory `window.beansChat`, `chat_widget.css`) mounts through a chat slot in `cc_base.html`, so every Control Center page inherits Timonel from the base. The chat-to-screen refresh contract (`beans:navigate` / `beans:refresh`), which assumed one Alpine scope with four tabs, is re-established per page: a chat action refreshes the page it is on and never claims to refresh a screen it cannot reach.
- **Alternatives.** (a) Include the widget on each page. (b) A dedicated `/chat` page only.
- **Why this won.** Chat is a shell concern; one mount gives every owner surface the assistant without the legacy page, and the asset loads once.
- **Why the alternatives lost.** (a) Per-page includes duplicate the mount and drift. (b) A chat-only page splits the assistant off the surfaces it should assist.
- **Panel source.** Winston, with Kaze on presence on every owner surface and Amelia on the refresh-contract break.

## Conventions

- **Naming.** New modules `agents/expander.py` (factory `create_expander_node`, pure helper `expand_items`) and `agents/attributes.py` (the single color and size vocabularies). SKUs stay `BC-{TYPE}-{DESCRIPTORS}` with discriminating tokens retained.
- **Structure.** Expansion logic is a pure function plus a thin node wrapper, mirroring decomposer's `should_decompose` plus `decompose` split. Unit tests live beside existing agent tests; goldens go in tests/eval.
- **Single vocabulary.** Colors and sizes are defined once in `agents/attributes.py` and imported by both the expander and the resolver's `VARIANT_HINT_TOKENS`. No second literal list.
- **Error handling.** Every new node fails open to the existing single-item path. No new node may raise into the graph; on any internal failure it returns the input items unchanged.
- **One writer per fact.** The expander owns the desired product set; the resolver owns reconciliation against catalog state; the database owns committed rows. The summary is built from returned database rows, never from input intent.
- **Observability.** The expander emits one assistant breadcrumb message per turn it acts on, in the decomposer's `[Expander] expanded N items` style.

### Costing domain conventions (spec 003)

- **Naming.** Costing tables snake_case plural; money in `*_cents` integers; currency a 3-letter code; FX as `fx_rate` numeric. New `backend/services/costing_service.py`; repositories and api under the existing `backend/repositories/` and `backend/api/` dirs.
- **Structure and errors.** Repository does SQL, service computes, api transports; the landed-cost snapshot is built in the service, never in a template or a query. A missing component is a completeness state, not an exception; a divide-by-zero in indirect allocation returns PENDING.
- **One writer per fact.** `input_purchases` owns input cost; `bom_lines` owns the recipe; `indirect_costs` owns overhead; the snapshot is derived; the FX rate belongs to its own purchase row. Suppliers never write margin, price, or another supplier's rows.
- **Observability.** Each landed-cost computation logs its completeness state and the inputs it read; the check-in scheduler logs every send.

### Control Center shell conventions (spec 003 reframe)

- **Module-registry contract.** A descriptor is `Module(id, label, route, headline, attention)`. Both providers are read-only, tenant-scoped, and bounded to one query each; one that fails returns a degraded headline or an empty list, never an exception.
- **Ownership.** A module owns its headline and its attention rules; the home and the attention service own only aggregation and ordering, never a threshold.
- **Role scope.** Supplier-scoped users (D-017) see only the modules their role permits; the home filters the registry by role, so a supplier never sees a margin tile.

### Control Center unification conventions (spec 004)

- **One owner base.** New pages extend `cc_base.html`. Never add a third owner-facing base. Legacy `base.html` is Admin-only.
- **One Alpine factory per page.** `productosDashboard`, `stockDashboard`, and so on, mirroring the legacy `tenantDashboard` split per domain.
- **Writes reuse endpoints.** Mutations go only through the existing `/api/tenants/{phone}/...` endpoints. No endpoint rewritten, no second write path. Soft-delete stays soft; stock adjust sends the signed delta; sale cancel restores stock.
- **Snapshot stays bounded.** Provider `snapshot()` is one bounded query and fails open. Page detail belongs in the route `_build_view`. New CRUD pages fetch client-side so they never join the snapshot pool.
- **Tiles are registry edits.** Tile wiring is a change to `registry.py`, never a home-template edit. Re-basing the home is gated by the pixel self-regression check, current home as golden.

## Non-goals

- No arbitrary natural-language attribute parsing. Only color lists and size lists in v1; everything else passes through.
- No new operation types. Expansion serves REGISTER_PRODUCT and REGISTER_PRODUCT_WITH_STOCK only.
- No change to the chat widget, channels, auth, or multi-tenant infra.
- No cross-turn memory of variant sets.

### Costing domain non-goals (spec 003)

- No live FX fetching in M1; the rate is hand-entered per purchase.
- No deletion or rewrite of sales, stock, expenses, or the assistant; the reframe is additive.
- No supplier visibility into margins, prices, or another supplier's costs, under any code path.
- No new Timonel operation beyond the one PRODUCTION_UPDATE intent.
- No general ledger or invoicing; this engine computes landed unit cost only.

### Control Center shell non-goals (spec 003 reframe)

- No central rules engine; attention rules stay in their modules.
- No tenant-configurable module registry in M1.
- No written scenario snapshots; scenarios are read-only.
- No client component framework; modules are server-rendered descriptors.

### Control Center unification non-goals (spec 004)

- No deletion or edit of the legacy page or its `base.html`; it stays the Admin-only fallback.
- No new or rewritten CRUD endpoints; new pages are surfaces over existing APIs.
- No change to auth, multi-tenant scoping, channels, or chat widget internals.
- No richer provider snapshots to feed tiles.
- No resolution of the #138 snapshot-pool performance debt; this spec must not regress the home and files against #138 if the pool saturates.
- No database objects; this spec adds no table, column, or migration.

## Open architectural questions

- **A-Q1.** Should expansion also serve sales ("vendi 5 medias azules y grises")? Disagreement: clean single-purpose node now versus a general fan-out. Fallback: ship REGISTER_PRODUCT only, leave the node general enough to extend. Tracked as spec OQ3.
- **A-Q2.** Does partial-success batch need an idempotency key so a retry of a half-landed batch does not double-create? Needs Dario's call; defensible fallback is to dedupe a retry by name within the owner's catalog. Tracked as spec OQ2.
- **A-Q3.** Pending-operation idempotency: an `op_token` column on the `sales` row, or an in-process committed-token set keyed by phone? Fallback: in-process set for v1 (single worker), a column when spec #63 lands durability. Tracked as spec 002 Q1. (D-010)
- **A-Q4.** Should resume serve ADD_STOCK paused on quantity in v1? Fallback: sale-needs-price only in M1, ADD_STOCK in M2. Tracked as spec 002 Q2. (D-012)
- **A-Q5.** Indirect allocation on a rolling trailing window or the current calendar month? Winston chose calendar month; Marcus argued a rolling window. Fallback: calendar month, PENDING until it has recorded production. Tracked as spec 003 OQ1. (D-015)
- **A-Q6.** Scheduler home: a Nomad periodic job or an in-process Baileys timer? Fallback: Nomad job, so cadence survives a connector restart. Tracked as spec 003 OQ2. (D-018)
- **A-Q7.** Static Python module registry or DB-driven registration? Fallback: a static list in `backend/modules/registry.py`; DB registration only if modules become tenant-configurable. (D-020)
- **A-Q8.** Attention computed on read or materialized? Fallback: on read in M1; materialize via the Nomad periodic seam when module count or query cost grows. (D-021)
- **A-Q9.** Headline aggregation is one bounded query per module per home load? Fallback: accept that at this module count; a combined aggregate query is a later optimization. (D-020)
- **A-Q10.** Migrate the four read-only pages in one styling-only cohort, or alongside each CRUD page? Fallback: one styling-only cohort right after the base extraction, so the brand converges before CRUD work. The pixel self-regression gate makes an early migration safe. (D-024)
- **A-Q11.** Does the eighth concurrent snapshot (productos) fit the pool within the deadline at live latency, or must #138 land first? Fallback: ship the shell and Productos with the bounded count and measure on the live cluster; resolve #138 before the later repoints only if saturated. (D-027)
- **A-Q12.** Record-sale on the new Ventas page: reuse the existing `POST /sales` shape, or does the missing modal need a contract the endpoint lacks? Fallback: build against the existing contract; treat any gap as a separate endpoint task. (D-025)

## Source

- Spec: ./specs/001-timonel-flexible-interpretation/spec.md
- Plan: ./specs/001-timonel-flexible-interpretation/plan.md
- Deliberation artifacts: ./specs/001-timonel-flexible-interpretation/.deliberation/
- Panelists who contributed to architecture decisions: Winston, with Amelia, Lattice and Mar'ah on D-004 through D-006.
- D-007 through D-012 (pending-operation completion): ./specs/002-timonel-pending-operations/spec.md and ./specs/002-timonel-pending-operations/plan.md. Panel: Winston (author), with Mary, Amelia, Bob, Edut, Mar'ah.

- D-013 through D-019 (production and landed-cost engine): ./specs/003-production-landed-cost-engine/spec.md and ./specs/003-production-landed-cost-engine/plan.md. Panel: Winston (author), with Amelia, Marcus, Bob, Kaze, Edut, Mar'ah.
- D-020 through D-023 (Beans Control Center shell, the spec 003 mid-run reframe): same spec dir. Reframe panel: Winston (author), with Compass, Bob, and Kaze plus Sally on the status-home mockup.
- D-024 through D-028 (Control Center unification, the single-product spec): ./specs/004-control-center-unification/spec.md and ./specs/004-control-center-unification/plan.md. Panel: Winston (author), with Amelia, Bob, and Kaze plus Sally on the unification mockup.

## Mode

This file was generated fresh on 2026-06-11 by /create-spec. Updated 2026-06-14 by /create-spec (spec 002 timonel-pending-operations) appending D-007 through D-012; D-001 through D-006 untouched. Updated 2026-10-13 by /create-spec (spec 003 production-landed-cost-engine) appending D-013 through D-019 and the costing domain addendum, conventions, non-goals, and A-Q5, A-Q6; D-001 through D-012 untouched. Updated again 2026-10-13 in the same run after Dario reframed the spec into the Beans Control Center, appending D-020 through D-023 (the command-center shell), the shell addendum, conventions, non-goals, and A-Q7 through A-Q9; D-019's default-landing clause is refined by D-023, the rest of D-013 through D-019 untouched. Updated 2026-10-14 by /create-spec (spec 004 control-center-unification) appending D-024 through D-028 (the single-product unification), the unification addendum, conventions, non-goals, and A-Q10 through A-Q12; D-001 through D-023 untouched. D-024 to D-028 build on D-020 and D-023.

---

## Spec 006 addendum — Simplify the Command Center (AI-first tabs), 2026-10-19

Mode: UPDATE. Scope: only the decisions impacted by collapsing nine nav entries into one to four AI-first tabs. Everything in D-001 through D-028 not named here is untouched. New decisions continue from the highest existing ordinal (D-028), so they begin at D-029.

### D-029: Tabs are a grouping attribute over the existing registry, not a new structure (refines D-020, D-023, D-026)

- **Chosen.** Add one field `group` to the `Module` descriptor (enum: `hoy`, `operacion`, `costos_produccion`). The rail renders each group as a tab; membership is data in `registry.py`. Three tabs in v1: Hoy (status home plus Timonel), Operación (productos, stock, ventas, caja), Costos y producción (costos, producción, logística, proveedores). Count lands at three, inside Dario's one-to-four bound.
- **Alternatives.** (a) A second tab-registry object mapping tab to a list of module ids. (b) Hard-code tab membership in `cc_base.html`. (c) One merged page per tab replacing the modules (see D-032).
- **Why this won.** The registry is already the single source of module truth. A grouping attribute keeps it so, and keeps adding or moving a module a one-field edit, never a template edit, preserving D-026 and Control Center AC1.
- **Why the alternatives lost.** (a) A second object duplicates identity and drifts from the registry. (b) Template hard-coding is the coupling D-020 forbids. (c) Merging is D-032's rejected path.
- **Implications.** The descriptor grows one field with a default, so an ungrouped module falls into Operación rather than vanishing. `href_for` and all routes are unchanged. Panel source: Winston.

### D-030: Timonel is promoted from the corner slot to a persistent primary column across all tabs (supersedes D-028's corner-widget placement clause dated 2026-10-14; keeps D-028's single-mount principle)

- **Chosen.** The chat widget still mounts exactly once through the slot in `cc_base.html` (D-028's single mount is kept). The slot becomes a persistent layout column on desktop and a dismissible sheet on mobile, not a bottom-right floating widget. On the Hoy tab the column is the primary action surface; on the other tabs it stays present as the operator.
- **Alternatives.** (a) Keep the corner widget. (b) A dedicated `/chat` tab only. (c) Duplicate the chat as a column per tab.
- **Why this won.** Dario is installing the AI to interact with everything. A corner widget signals secondary; a primary column signals primary. One mount still serves every tab, so the asset still loads once.
- **Why the alternatives lost.** (a) The corner contradicts the brief. (b) A chat-only tab splits the assistant off the surfaces it should assist, the exact reason D-028 rejected it. (c) Per-tab duplication drifts, violating D-028's one-mount rule.
- **Implications.** `cc_base.html` becomes a two-region shell: a Timonel column and the tab content region, collapsing to a single column plus chat sheet on mobile. The factory `window.beansChat` is unchanged; only its container and CSS change. Panel source: Winston, with Kaze on presence on every owner surface.

### D-031: The chat-to-content contract extends `beans:navigate` / `beans:refresh` with a tab dimension; it is not replaced

- **Chosen.** The `beans:navigate` payload gains `{tab, module}`. A small shell tab-router listens, switches tab if needed, then drills to the module panel or page. `beans:refresh` keeps its per-surface semantics from D-028: a chat action refreshes the content currently mounted and never claims to refresh a surface it cannot reach.
- **Alternatives.** (a) A new event bus. (b) A full page reload on every chat action. (c) A global refresh-all.
- **Why this won.** The bridge already exists (`cc_chat_bridge.js`). Adding a tab field is the minimal extension and preserves D-028's honesty rule about never claiming an unreachable refresh.
- **Why the alternatives lost.** (a) A new bus duplicates a working contract. (b) Reload loses Alpine state and fights the no-store model. (c) Refresh-all re-pays every snapshot, the regression D-027 guards.
- **Implications.** The shell owns a tiny tab-router mapping `{tab, module}` to the right content; when the target is not mounted it navigates the module route. Panel source: Winston, with Amelia on the contract extension.

### D-032: The eight per-module pages are kept as drill-downs behind tabs, not merged

- **Chosen.** Each module keeps its route, its `_build_view`, and its single Alpine factory (D-025). A tab is a container of its modules' surfaces, reached as tiles that drill in to the existing page, or by Timonel navigation. No mega-page, no combined factory.
- **Alternatives.** (a) Merge each tab's modules into one combined page and factory. (b) Delete the less-used modules.
- **Why this won.** The three-read-layer split (snapshot, `_build_view`, api) and the one-factory-per-page convention are what keep each surface cheap and independently testable. Merging re-couples them and discards proven CRUD. Simplifying the nav is a presentation goal, not a reason to rebuild domains.
- **Why the alternatives lost.** (a) A merged factory owns four domains' mutations at once, a fragile object that re-introduces the coupling D-020 removed. (b) Deleting modules loses function the owner still needs occasionally.
- **Implications.** Operación and Costos y producción each render their modules' headline tiles (reusing the provider snapshots) with drill-in to the existing page. Default: a tab shows its modules' tiles; the inline-primary-module variant is A-Q15. Panel source: Winston.

### D-033: Tabs reuse the existing snapshot fan-out; `home_service` groups by tab, no new data path

- **Chosen.** `home_service.build_home` still fans out one `snapshot()` per module concurrently, under the D-027 bound unchanged. The result is grouped by the registry `group` field into per-tab tile sets. Hoy shows the full status home plus the attention strip as today; Operación and Costos render the subset of tiles for their group. No new query, no new service.
- **Alternatives.** (a) A per-tab service that re-queries on tab switch. (b) Lazy per-tab snapshot fetch.
- **Why this won.** The fan-out is already concurrent and bounded. Grouping its output is free and keeps one data path and the 0.9s render.
- **Why the alternatives lost.** (a) Re-querying per tab multiplies load on the pool D-027 protects. (b) Lazy fetch adds a second path for no measured need at this module count.
- **Implications.** `build_home` returns grouped tiles, or the template groups by the `group` field at render; attention stays global on Hoy. If the #138 pool debt bites, it bites once at home load as today, never per tab switch. Panel source: Winston, grounded in D-027.

## Conventions

- Tab membership is the registry `group` field, never a template literal. A new module joins a tab by setting one field.
- Three tabs in v1: Hoy, Operación, Costos y producción. Labels Spanish. The count stays within one to four.
- The Hoy tab is the default landing; it is D-023's status home plus the Timonel column, so D-023's default-landing clause stands unchanged.
- Timonel mounts once (D-028 kept); the change is its container and CSS, not its factory.
- `beans:navigate` carries `{tab, module}`; `beans:refresh` stays per-surface and never claims an unreachable refresh.

## Non-goals

- No merging of module pages, no new or rewritten CRUD, no API change (D-032).
- No change to auth, multi-tenant scoping, channels, or the D-027 snapshot bound.
- No new data path; the `home_service` fan-out is unchanged (D-033).
- No tenant-configurable tabs in v1.
- No removal of any module.

## Open architectural questions

- **A-Q13.** Three tabs, or two (fold Costos y producción into Operación), or four (split logística and proveedores out). Fallback: three, re-grouped by observed use after 30 days, since it is one field edit. Panel source: Winston.
- **A-Q14.** Timonel column on the left or the right, and on mobile does it persist or collapse to a launcher. Fallback: right column on desktop, collapsible sheet on mobile.
- **A-Q15.** On Operación and Costos, tiles-with-drill-in or a primary module rendered inline with a sibling rail. Fallback: tiles with drill-in, the cheapest and the one that reuses the snapshots; revisit if the owner bounces too much.
- **A-Q16.** Does a money write through Timonel require a visible confirmation card on the active tab before it is considered done. Fallback: yes, surface the written row inline via `beans:refresh`; needs Edut and Mar'ah on the trust question raised in the review. Panel source: Winston, with Edut and Mar'ah.

---

## Spec 007 addendum — Native tool-use chat (retiring the Gemini LangGraph Timonel), 2026-10-19

Mode: UPDATE. Scope: only the decisions that swap the chat brain to a native Claude tool-use loop. Everything in D-001 through D-033 not named here is untouched. New decisions continue from the highest existing ordinal (D-033), so they begin at D-034. This addendum composes with the Spec 006 Simplify addendum: that spec reshaped Timonel's container (tabs, primary column); this spec swaps the brain inside it. D-034 retires the graph the System-shape section and D-001 through D-019 describe, so that pipeline is superseded as the live brain while its decision history stays for the record; D-038 reuses D-008 through D-010.

### D-034: The chat brain is a native tool-use loop on the gateway; the LangGraph is retired

- **Chosen.** Replace the body of `ChatService.chat_with_tenant` with one tools-enabled gateway loop. Delete `graph.py` and `agents/*` (router, decomposer, expander, resolver, safe_node, state).
- **Alternatives.** (a) Keep the graph and re-point one node at tools. (b) An app-mediated tool loop where the app, not the model, drives the tool calls (Winston's prior recommendation).
- **Why this won.** One reasoner over a fixed tool set removes the router and resolver classification drift specs 001 and 002 fought, and extending the assistant becomes one tool plus one endpoint, not another graph node and prompt.
- **Why the alternatives lost.** (a) Keeping the graph keeps every fragile hop. (b) The app-mediated loop was overruled by Dario on 2026-10-16, who chose native tool-use on the box.
- **Implications.** D-022 COST_SCENARIO becomes a read tool; D-018 PRODUCTION_UPDATE routes into the same brain. `llm_gateway.py` is kept and reused.
- **Panel source.** Winston, grounding Dario's binding choice.

### D-035: Tools are a narrow MCP server; built-ins disallowed; only `mcp__beans__*` allowlisted; no skip-permissions

- **Chosen.** The child runs `--max-turns` greater than 1 with `--allowedTools mcp__beans__*` as the only positive grant, the existing built-in `--disallowedTools` list kept in full, `--strict-mcp-config` pointing only at the beans server, and `--dangerously-skip-permissions` never passed. One child per request, disposed after.
- **Alternatives.** (a) `--dangerously-skip-permissions` with a disallow list. (b) Tools off, the retired spec 005 design.
- **Why this won.** Allowlisting only our tools and omitting skip-permissions means, with no TTY in headless, anything off the allowlist still auto-denies: two independent gates, neither one typo from a built-in running.
- **Why the alternatives lost.** (a) skip-permissions is one disallow-list typo from remote code execution. (b) Tools off cannot drive native tool-use.
- **Implications.** The pool lifecycle moves from one turn per child to one request per child; warmth and cross-request isolation both hold because each request gets a fresh disposed child. A boot-time tool-posture self-check (below, conventions) enforces the allowlist.
- **Panel source.** Winston, grounding Tamir.

### D-036: Tools hold no DB credentials; they call an authenticated internal operation API; side effects are observed there

- **Chosen.** Tools call back to FastAPI internal endpoints gated by the existing `INTERNAL_SERVICE_TOKEN` seam (`_has_internal_token` in `backend/auth/dependencies.py`), which run the operation under `tenant_context`. Cache invalidation and the navigation cue are emitted at commit, not parsed from gateway output. The domain guards in `write_agent` (NULL-price block, batch partial-success summary, ADD_STOCK disambiguation, product resolution, SKU generation) move into these endpoints.
- **Alternatives.** (a) A DB connection on the box. (b) Let the model report its own side effects.
- **Why this won.** The box stays a pure reasoner; the app that already owns the DB owns re-validation and every side effect, where `tenant_context` and `cache.invalidate_all` already live.
- **Why the alternatives lost.** (a) A DB credential on the box is one injection from the ledger. (b) Trusting model-reported effects trusts effects an injection can fabricate.
- **Implications.** The box gains two non-DB secrets (the operation-API base and a scoped bearer); the Nomad allowlist self-check extends to cover the operation-API host.
- **Panel source.** Winston, with Amelia on reusing the endpoint contracts.

### D-037: Tenant scope is injected out of band, never a model-settable tool parameter

- **Chosen.** The gateway pins the session-resolved phone into the per-request MCP server environment; the tool callback carries it, the model never sees or sets it, and FastAPI re-validates scope on every call.
- **Alternatives.** (a) `phone` as a model-filled tool argument. (b) Hardcode the one phone.
- **Why this won.** A scope the model cannot express is a cross-tenant surface that cannot be injected, now or when multi-tenant returns.
- **Why the alternatives lost.** (a) A model-filled `phone` is the injection target itself. (b) Hardcoding blocks the reversible multi-tenant future for no gain.
- **Panel source.** Winston, grounding Tamir.

### D-038: Writes are two-phase; the commit is a non-model, operator-clicked endpoint

- **Chosen.** Write tools only stage a validated preview and mint an `op_token` in the server-side pending store (reusing D-008 and D-010). The model surfaces it as a confirm card. The commit happens only on the operator's click, posting the token to a session-authenticated `/chat/confirm` endpoint for which the model has no tool.
- **Alternatives.** (a) A commit tool the model calls. (b) Direct commit inside the loop.
- **Why this won.** Removing commit from the model's capability set means a fully hijacked model can only propose; the injection-to-write surface spec 005's council closed stays closed.
- **Why the alternatives lost.** (a) A commit tool lets an injected confirmation fire it. (b) Direct commit has no human gate at all.
- **Implications.** The confirm card is a new `metadata` variant on the unchanged envelope, rendered by `chat_widget.js`, reusing D-009. The confirm token is app-minted, args-bound, single-use, and short-TTL. The Spec 006 Simplify A-Q16 (does a money write require a visible confirmation card) is answered yes here and made structural.
- **Panel source.** Winston, with Edut on consent and Tamir on the write boundary.

### D-039: Single business resolves the phone from the session; the brain ignores any client-supplied phone

- **Chosen.** The URL keeps `{phone}` for route compatibility, but for scope the brain uses the phone `require_tenant_match` already resolved from `beansco_session`, ignoring the path value.
- **Alternatives.** (a) Trust the URL `{phone}`. (b) Drop `{phone}` from the route now.
- **Why this won.** The session is already the scope authority; using it closes a client-controlled input without breaking the deployed widget.
- **Why the alternatives lost.** (a) The URL value is client-controlled. (b) Dropping it now needlessly breaks a live widget.
- **Panel source.** Winston.

### Conventions (spec 007)

- **Tool naming.** `mcp__beans__<verb>_<noun>`: reads `read_*`, write previews `preview_*`. There is no `commit_*` tool and never will be; commit is not a model capability (D-038).
- **Internal API shape.** `POST /internal/ops/{op}` under internal-token auth, 1:1 with the `database_config.py` functions, tenant taken from the pinned scope and never from the body. Previews return `{op_token, preview, missing_fields}`; reads return the module snapshot shapes.
- **Boot tool-posture self-check.** The gateway entrypoint asserts at boot that the running `claude` allows only `mcp__beans__*` and exits non-zero otherwise, symmetric with the existing secret-shape grep. The secret grep guards leakage; this guards tool execution, the leg native tool-use removes.
- **How writes confirm.** Preview stages, the human clicks, and `/chat/confirm` consumes the single-use token under `tenant_context`. That is the only place a row commits and the cache invalidates. No confirm gate may be auto-satisfied by model output.
- **One writer per fact.** The internal API owns committed rows, the pending store owns staged intent, and the acknowledgement is built from returned rows, never from the model's memory of the proposal.
- **Honesty of acknowledgement.** A post-write message names the SKU or target, the amount in digits, and the resulting balance, read back from the commit response.

### Non-goals (spec 007)

- No built-in tools ever on the box, no DB credentials on the box, no commit capability exposed to the model.
- No change to the envelope, the widget seam, auth, or `tenant_context` beyond the confirm-card metadata variant.
- No new operation types; this spec ports the existing menu, it does not grow it.
- No multi-tenant rollout; one business, with scope injected as if there could be many.
- No change to the onboarding chat, which stays a separate Gemini tool-calling dispatcher.

### Open architectural questions (spec 007)

- **A-Q17.** Shared `INTERNAL_SERVICE_TOKEN`, or a per-request token scoped to one phone with a short TTL? Fallback: the existing token with the pinned phone and FastAPI re-validation for M1; per-request minting if the callback path widens. (D-036, D-037)
- **A-Q18.** Does the confirm card need a server-issued nonce bound to the `op_token`? Fallback: session auth plus the single-use args-bound token for M1; add a nonce if `/chat/confirm` is ever reachable without the session. (D-038)
- **A-Q19.** Does `--max-turns` alone bound the loop, or is a per-request tool-call budget also needed? Fallback: cap `--max-turns` low, measure live, add a tool-call counter if a turn loops. (D-035)
- **A-Q20.** Keep the gateway `/run` tool-free path beside the new tool path, or retire it with the graph? Fallback: keep `/run` tool-free until nothing calls it, then retire. (D-034)

### Source (spec 007)

- D-034 through D-039 (native tool-use chat, retiring the Gemini LangGraph Timonel): ./specs/007-native-tool-use-chat/spec.md and ./specs/007-native-tool-use-chat/plan.md. Panel: Winston (author), with Amelia, Bob, Kaze, Edut, Tamir, and Compass.
