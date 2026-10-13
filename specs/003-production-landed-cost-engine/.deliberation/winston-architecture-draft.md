# Architecture-author addendum: Production and Landed-Cost Engine

Mode: update. Appends to `beans-assistant/ARCHITECTURE.md`. New decisions start at D-013; D-001 through D-012 untouched.

## System shape

A new per-tenant domain hanging off the existing `products` table, computing one derived fact: landed cost per bracelet type, per country, in USD, with a completeness state. Inputs, purchases, BOM, labor, packaging, logistics, customs, and indirect costs are raw facts entered once each; landed cost is always computed, never hand-entered. Suppliers become scoped users of the same tenant via a new membership layer. Check-ins reuse Baileys and Timonel. The UI makes costing the home surface without deleting sales, stock, or expenses.

| Module | Owns |
|--------|------|
| costing schema (new per-tenant tables) | raw cost facts |
| suppliers repository/api | supplier rows |
| costing_service | the derived snapshot + allocation |
| tenant_members (public) | who may reach a tenant |
| checkin scheduler | send cadence + log |
| costing home | costing routes/templates |

## Decision log

### D-013: `products` is the bracelet-type anchor; costing in new tables

- **Chosen.** One bracelet type stays one `products` row. New costing tables, keyed by product_id or country: suppliers, cost_inputs, input_purchases, bom_lines, labor_costs, packaging_costs, shipping_lanes, customs_duties, indirect_costs, landed_cost_snapshots.
- **Alternatives.** (a) a separate `bracelet_types` table; (b) costing columns onto `products`.
- **Why won.** `products` already carries SKU and is referenced by sales, stock, and sale_items. It is the one existing identity for a bracelet type.
- **Why lost.** (a) forks identity into two sources of truth. (b) costing is many rows per product per country, not flat columns on one row.
- **Implications.** `create_tenant_schema` gains the tables plus a backfill. Landed cost is a derived snapshot, not a `unit_cost_cents` write.
- **Source.** Winston.

### D-014: Input purchases store original currency, FX rate, and USD; append-only

- **Chosen.** `input_purchases` stores original_currency, original_amount_cents, fx_rate, usd_amount_cents, purchased_at. The rate is hand-entered in M1. A correction is a new row, never an in-place edit.
- **Alternatives.** (a) USD only; (b) original plus a fetched live rate.
- **Why won.** The triplet is a full audit trail: a disputed cost is re-checkable and a wrong rate is visible.
- **Why lost.** (a) hides a wrong rate. (b) a live rate drifts from the rate actually paid; a fetched rate is a later default, not the stored truth.
- **Implications.** A USD normalization helper sits beside the repository; a rate edit means a new row and snapshot.
- **Source.** Winston.

### D-015: Indirect allocates per unit produced, per country, per month

- **Chosen.** Indirect per bracelet = total indirect cost for a country in a month, divided by units produced there that month. Display stands and overhead use this basis.
- **Alternatives.** (a) per revenue; (b) per batch.
- **Why won.** Per-unit-produced is the honest denominator and does not depend on the price we are computing.
- **Why lost.** (a) is circular: price is the output, so allocating by revenue defines the answer in terms of itself. (b) batches are uneven; display stands are not per-batch.
- **Implications.** `costing_service` needs a per-country per-month production count; a zero-production month renders indirect PENDING.
- **Source.** Winston.

### D-016: The snapshot carries a completeness state, never a false total

- **Chosen.** A snapshot holds each component (materials, labor, packaging, shipping, customs, indirect) with a filled/pending status and a completeness enum. The partial total renders beside the list of pending ones.
- **Alternatives.** (a) block computation until complete; (b) treat pending as zero.
- **Why won.** The CEO said some numbers are not known yet. Gaps are the normal state, and a visible gap is the prompt to fill it.
- **Why lost.** (a) no number ever renders. (b) silently understates cost and the CEO prices on a lie.
- **Implications.** Every costing surface reads the completeness state; a complete total is a distinct, earned state.
- **Source.** Winston, Mar'ah.

### D-017: Supplier-as-user is a membership model, not a role flag

- **Chosen.** Add `public.tenant_members` mapping an app_user to a tenant phone with a role (owner or supplier) and an optional supplier_id. `require_tenant_match` resolves a member to the tenant. Supplier queries filter by supplier_id; cost, price, and margin are owner-only.
- **Alternatives.** (a) a tenant schema per supplier; (b) a role column on app_users alone.
- **Why won.** One tenant with several scoped users is the requirement: the CEO sees the whole model, each supplier only their own rows.
- **Why lost.** (a) fragments the data so the CEO cannot consolidate. (b) the phone-keyed guard cannot express many-users-one-tenant, so suppliers cannot log in or they over-read.
- **Implications.** Touches the auth kernel, so not autodev. The within-tenant scope is a server-side read filter, never a template.
- **Source.** Winston, with Edut and Mar'ah on consent and harm.

### D-018: Check-ins reuse Baileys outbound and Timonel

- **Chosen.** A periodic scheduler calls the existing Baileys outbound to send a check-in. Replies route back through Timonel with a new PRODUCTION_UPDATE intent. A non-parsing reply is stored verbatim as a note to the CEO; it never force-writes and is never dropped.
- **Alternatives.** (a) a second bot or channel; (b) a parser separate from Timonel.
- **Why won.** The channel and the interpreter already exist; a check-in is one more intent, not one more system.
- **Why lost.** (a) the context packet forbids a second channel. (b) duplicates Timonel and splits the truth of how a message is read.
- **Implications.** The scheduler owns cadence and a send log; the sender identifies the business truthfully. External send ships behind the sacred gate.
- **Source.** Winston, with Mar'ah and Edut.

### D-019: The UI reframe is additive; nothing is deleted

- **Chosen.** A new costing home route and template become the default landing surface; nav reorders so sales, stock, and expenses sit as secondary sections. No existing route or template is removed.
- **Alternatives.** rebuild the dashboard around costing.
- **Why won.** "Reencuadrar, no borrar." Reordering preserves working code.
- **Why lost.** A rebuild tears out proven layout code, which the directive forbids.
- **Source.** Winston, grounding Dario.

## Conventions

- **Naming.** Tables snake_case plural; money in `*_cents` integers; currency a 3-letter code; FX as `fx_rate` numeric. New `backend/services/costing_service.py`; repositories and api under their existing dirs.
- **Structure and errors.** Repository does SQL, service computes, api transports; the snapshot is built in the service, never in a template or query. A missing component is a completeness state, not an exception; divide-by-zero returns PENDING.
- **One writer per fact.** `input_purchases` owns input cost; `bom_lines` the recipe; `indirect_costs` overhead; the snapshot is derived; the FX rate belongs to its purchase row.
- **Observability.** Each computation logs its completeness state and inputs read; the scheduler logs every send.

## Non-goals

- No live FX fetching in M1; manual rate per purchase.
- No deletion or rewrite of sales, stock, expenses, or the assistant.
- No supplier visibility into margins, prices, or others' costs.
- No new Timonel operation beyond PRODUCTION_UPDATE.

## Open architectural questions

- **A-Q5.** Indirect allocation on a rolling trailing month or the current calendar month? Fallback: calendar month, PENDING until it has recorded production.
- **A-Q6.** Scheduler home: a Nomad periodic job or an in-process Baileys timer? Fallback: Nomad job, so cadence survives a connector restart.

## Source

- Context: ./context.md. Existing: beans-assistant/ARCHITECTURE.md (D-001 to D-012). Grounded in database_pg.py, auth/dependencies.py, app_users_repository.py, graph.py, whatsapp_baileys/.
- Panel: Winston, with Mar'ah and Edut on D-016, D-017, D-018.
