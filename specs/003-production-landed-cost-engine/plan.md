# Plan: Beans Control Center

## Architecture sketch

The platform becomes a command-center shell. A static module registry holds one descriptor per domain, each exposing two read-only providers: a `headline` (the module's one number for its home tile) and `attention` (the module's list of items for the strip). The status home at the default route iterates the registry, renders a tile per module, and an attention service aggregates, sorts by severity, and caps the strip. The shell owns no domain logic. On FastAPI and Jinja a module is a server-side descriptor over the existing api, service, and repository triple, not a frontend component. Costing numbers live in stored snapshots and are always shown; a pure `recompute(snapshot, overrides)` serves both the stored build and a read-only assistant scenario path. Full decision log in `ARCHITECTURE.md`, D-013 through D-023.

```
backend/modules/registry.py  -> [ Module(id, label, route, headline, attention), ... ]
            |
   backend/api/home.py  (default route "/")
            |  iterates registry
   +--------+---------+----------------+-------------------+
   v        v         v                v                   v
 Stock    Caja     Ventas          Costos             Producción / Proveedores / Logística
 (exists) (exists) (exists)        (new, D-013..16)    (new modules)
   \        \        \                |                   /
    \        \        \     headline() + attention()    /
     -------------------> status home tiles + attention strip

attention_service.py  -> aggregate module.attention(), sort by severity, cap
costing_service.recompute(snapshot, overrides)  -> Timonel COST_SCENARIO (read-only)
public.tenant_members (auth kernel)   whatsapp_baileys + Timonel (gated)
```

## Sequencing

| Milestone | Theme | Covers | Rough effort | Gate |
|-----------|-------|--------|--------------|------|
| M1 | Shell plus status home over the EXISTING sales, stock, expenses data | S1, S2 | 6 tasks | none |
| M2 | Costing module (new tables, multi-currency, landed cost, completeness, tile) | S3 | 4 tasks | none |
| M3 | Production module and cost-domain breadth | S4 | 4 tasks | none |
| M4 | Multi-country, indirect allocation, margin, Logística module | S5 | 4 tasks | none |
| M5 | Suppliers directory, overdue-check-in signal, assistant scenario read-path | S6 | 3 tasks | none |
| M6 | Supplier self-service login (auth kernel first) | S7 | 3 tasks | S7 named-human-signoff (Andreas) |
| M7 | Automated WhatsApp check-ins | S8 | 3 tasks | S8 named-human-signoff (Dario, Re'i) |

The inversion from the first draft, per Bob and Winston: the shell and the home over data that already exists land first, because they need no new data model, deliver the nucleus the CEO asked for, and set the registry-plus-attention contract every later module plugs into. Costing is the second module, not the first, because its tables are net-new and nothing on the home depends on them. M3 production and M4 counts feed the indirect denominator; M5's scenario read-path needs M4's stored numbers; M6 and M7 come last behind their named human gates.

## Risks

1. **The home couples to every module.** If the home template hard-codes each tile, every new module edits the home. Mitigation: the module registry and the two-provider protocol (D-020) land first in M1 and are the only contract the home knows.
2. **One slow or broken module takes down the whole home.** A synchronous headline query per module is an N-across-modules page load. Mitigation: each provider is bounded to one query and fails to a degraded tile, never raising into the page (AC3).
3. **The attention strip becomes noise.** With no severity order, no cap, and soft thresholds, the strip turns into an ignored second to-do list. Mitigation: the attention service sorts by severity and caps the strip (AC4); every signal has a concrete trigger and a clear action, and the thresholds codify the CEO's existing rhythm rather than a new one (Compass).
4. **A false-precise landed cost or FX drift.** A missing line rendered as a finished number, or a USD figure captured at a stale rate, misleads a price or location decision. Mitigation: the completeness state (AC8) and the stored original-plus-rate-plus-USD triplet (AC7).
5. **An external message that burns a real relationship.** Mitigation: the whole send path is human-gated (AC15, AC16, AC17), opt-in, truthful sender, cadence cap, and a verbatim-keep fallback.

## Dependencies

- The module registry and provider protocol (M1) are the contract every later module meets.
- The repo's schema-per-tenant Postgres and `create_tenant_schema` imperative DDL; the costing forward migration reuses the `register_products_batch` SAVEPOINT discipline.
- `backend/auth/dependencies.py` `require_tenant_match` and `app_users` for the M6 membership change.
- `whatsapp_baileys/` Baileys connector and the Timonel pipeline (`graph.py`, `agents/`) for the M5 scenario read-path and the M7 check-ins.
- The push account is `eldaroo`; the Nomad cluster for the optional scheduler job (OQ2).
- External data dependency: the CEO's bracelet-type inventory (OQ6), a fixture and real-costing seed, not a build blocker.

## Cost-shaped considerations

- The local dev disk is at 2GB free. M1 through M5 are Python and Jinja changes with a light test suite and will run; any heavy `npm install` in `whatsapp_baileys/` for M7, or a fresh container build, needs space freed first.
- The deploy path is the known one for this repo: merge to master, build and push the image, patch the Nomad job directly with the `eldaroo` token because the job has no auto-revert. Unchanged by this spec.
