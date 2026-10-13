# Beans Control Center addendum (spec 003 reframe, 2026-10-13)

Append-only delta; new decisions start at D-020. D-001 to D-019 untouched.

## System shape

The platform becomes a command-center shell: a status home rendering one tile per registered module plus an attention strip. The shell owns no domain logic, only a module registry and two provider contracts. Each module is an existing or new triple of api, service, and repository that also exposes a headline and an attention provider. The home aggregates by iterating the registry, never importing a module's internals. On FastAPI and Jinja there is no client component model, so a module is a server-side descriptor plus a provider protocol, not a frontend widget. Costing numbers live in stored snapshots and are always shown; scenario exploration is a read-only recompute run by the assistant.

## Module plug-in table

| Module | Route | Headline number | Attention rule | Status |
|--------|-------|-----------------|----------------|--------|
| Home / Panel | `/` | aggregates all | aggregates all | new shell |
| Producción | `/produccion` | units this week | arrival cadence overdue | new |
| Proveedores | `/proveedores` | active suppliers | overdue check-in | new |
| Costos y margen | `/costos` | margin per country | pending cost component | new, reuses D-013 to D-016 |
| Inventario / Stock | `/stock` | low-stock count | low coffee stock | existing, +providers |
| Ventas | `/sales` | sales this week | none in M1 | existing, +providers |
| Caja / Gastos | `/expenses` | cash balance | negative cash signal | existing, +providers |
| Logística | `/logistica` | open lanes | pending customs line | new |
| Asistente (Timonel) | `/chat` | not a tile | n/a | existing, +scenario read-path |

## Decision log (new)

### D-020: The home is a module registry plus a provider protocol

- **Chosen.** A static registry of module descriptors in `backend/modules/registry.py`. Each carries id, Spanish label, route prefix, and two callables: `headline(tenant, user) -> Headline` and `attention(tenant, user) -> list[AttentionItem]`. The status home iterates the registry, rendering one tile per descriptor plus the attention strip.
- **Alternatives.** (a) a home template that hard-codes each tile; (b) a DB-driven registry.
- **Why won.** One headline per module aggregates through a uniform contract, so adding a module is a descriptor plus two methods, never a home edit. It fits the repo: each module already owns an api, service, and repository.
- **Why lost.** (a) couples the home to every module. (b) modules are code, not data; the indirection has no caller.
- **Implications.** A `Headline` dataclass (value, unit, Spanish label, status, href) and an `AttentionItem` dataclass. Providers are bounded and fail to a degraded tile, never raising into the page, per the repo's fail-open convention.
- **Panel source.** Winston.

### D-021: Attention rules live in the module that owns the data, computed on read

- **Chosen.** Each module's `attention()` provider produces its own items (low stock, pending cost component, overdue supplier check-in, negative cash). `backend/services/attention_service.py` aggregates across the registry, sorts by severity, and caps the strip.
- **Alternatives.** (a) a central rules engine; (b) materialized attention rows.
- **Why won.** The module owns the data and the threshold meaning, so the rule belongs with it. A central engine would reach into every module's internals, the coupling D-020 forbids.
- **Why lost.** (a) centralizes knowledge the module owns. (b) adds a write path and staleness with no cost reason yet.
- **Implications.** An `AttentionItem` carries severity, module id, Spanish message, href, and a dedupe key; the strip orders by severity so it is not a second to-do list.
- **Panel source.** Winston, with Kaze on the strip not becoming noise.

### D-022: Costing scenarios are a read-only recompute the assistant runs (refines D-013 to D-016)

- **Chosen.** The stored `landed_cost_snapshots` are the source of truth and always shown. A pure `costing_service.recompute(snapshot, overrides) -> snapshot` computes a hypothetical in memory. Timonel gains one read-only COST_SCENARIO path that loads a snapshot, applies an override (for example, moving display-stand production to Colombia), and returns the recomputed number, never writing.
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

## Conventions (new)

- **Module-registry contract.** A descriptor is `Module(id, label, route, headline, attention)`. Both providers are read-only, tenant-scoped, and bounded to one query each; one that fails returns a degraded headline or an empty list, never an exception.
- **Ownership.** A module owns its headline and its attention rules; the home and attention service own only aggregation and ordering, never a threshold.
- **Role scope.** Supplier-scoped users (D-017) see only the modules their role permits; the home filters the registry by role, so a supplier never sees a margin tile.

## Non-goals (new)

- No central rules engine; attention rules stay in their modules.
- No tenant-configurable module registry in M1.
- No written scenario snapshots; scenarios are read-only.
- No client component framework; modules are server-rendered descriptors.

## Open architectural questions (new)

- **A-Q7.** Static Python registry or DB-driven registration. Fallback: a static list in `backend/modules/registry.py`; DB registration only if modules become tenant-configurable.
- **A-Q8.** Attention computed on read or materialized. Fallback: on read in M1; materialize via the Nomad periodic seam (as in D-018) when module count or query cost grows.
- **A-Q9.** Headline aggregation is one bounded query per module per home load. Fallback: accept that at this module count; a combined aggregate query is a later optimization.

## Unchanged from D-013 to D-019

D-013 (products anchor, ten costing tables), D-014 (FX triplet, append-only), D-015 (indirect per unit, country, month), D-016 (completeness state), D-017 (supplier membership and within-tenant scope), and D-018 (Baileys/Timonel check-in reuse plus the sacred gate) all stand. D-019 stands except its default-landing clause, which D-023 refines.
