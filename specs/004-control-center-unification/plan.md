# Plan 004: Control Center as the single owner product

## Architecture sketch

One owner-facing base, extracted from the already-shipped home, that every page extends.
CRUD arrives as Alpine over the endpoints that already exist. Routing stays registry-driven.
The three read layers stay distinct and keep their own cost and failure mode.

```
                       cc_base.html  (owner shell: modern Control Center design, held nav, theme, Timonel slot)
                            |  extends
   +----------+-------------+-------------+-------------+-------------+
   |          |             |             |             |             |
 home      productos      stock         ventas       resultado   costos/prod/log/prov
 (tiles)   (ABM)          (CRUD)        (CRUD)        (CRUD)      (read-only, migrated)
   |          |             |             |             |             |
   |     Alpine factory per page  ->  existing /api/tenants/{phone}/... endpoints (reused, never rewritten)
   |
 registry.py  (one descriptor per module; tile + route + provider)  -- single source of module truth

Three read layers, never merged:
  provider snapshot()  = the home tile number   (one bounded query, fail-open)
  route _build_view()  = the page initial paint (tenant-scoped, no-store, off-loop)
  /api endpoints       = the Alpine CRUD path   (the only write path)

Legacy base.html + /tenants/{phone}  ->  unchanged, Admin-only fallback.
```

Reference: ARCHITECTURE.md decisions D-024 (shared base), D-025 (Alpine over existing endpoints,
three read layers), D-026 (registry-driven routing), D-027 (bounded snapshot, eighth concurrent),
D-028 (Timonel in the base).

## Sequencing

The panel corrected the naive order. Unified design is NOT last. The shared base is the foundation
seam and ships first, so every new page is born extending it and is written once. The four existing
read-only pages migrate right after, behind a visual self-regression check, so the brand converges
before CRUD work. Then the CRUD pages, one domain per step. Timonel and the demote-legacy verify close it.

| Cohort | Milestone content | Surfaces | Rough effort | Leaves the live product |
|--------|-------------------|----------|--------------|--------------------------|
| A | Shared `cc_base.html` extracted from home; modern Control Center design tokens (indigo/Inter, the look kept per Dario); held nav; page-enter transition; empty-state + skeleton components; Timonel slot; re-base the home (pixel-gated); migrate the 4 read-only pages onto the base | S1-shell, S6-legacy-pages-migrated, S7-timonel-everywhere (slot) | 3 to 4 days | One modern design across the owner surface; still bounces Resultado/Stock/Ventas |
| B | `productos` module + page (ABM); `/stock/{phone}` page + repoint | S2-productos, S3-stock | 2 to 3 days | Productos and Stock native; Ventas/Resultado still bounce |
| C | `/ventas/{phone}` (list, cancel, view-detail, record-sale build) + repoint; `/resultado/{phone}` (ingresos/ganancia + expenses) + repoint + mislabel fix | S4-ventas, S5-resultado | 2 to 3 days | Every tile native; nothing bounces |
| D | Timonel refresh contract across pages; remove every owner-facing link into legacy; crawl verify; perf confirm on the live cluster | S7-timonel-everywhere, S8-demote-legacy | 1 to 2 days | No owner path reaches legacy; home still under 1s |

Each cohort is live-verifiable on its own and never bounces a tile a prior cohort already claimed.
This is the one-cohort-per-/develop-session granularity.

## Risks

1. Re-basing the deployed home silently regresses it (spacing or color shifts by a pixel).
   Mitigation: extract the base FROM the current home so it is byte-equal by construction, and gate the
   re-base with a visual self-regression check, current home as golden. Do not redesign during extraction.
2. CRUD pages drift from the reused endpoint contracts or double-write. The endpoints carry invariants
   (soft-delete, signed stock delta `newQty - currentQty`, cancel-not-destroy, stock-restoring cancel).
   Mitigation: one Alpine factory per page calling the existing endpoints and refetching; no second write
   path; the signed-delta conversion is ported verbatim and asserted in the Stock AC.
3. The eighth concurrent snapshot (productos) pushes the home past its deadline at live cross-container
   latency (the open #138 debt). Mitigation: the productos snapshot is one bounded count, fail-open; CRUD
   pages are client-fetch so they stay off the snapshot pool; AC10 measures the live home and files against
   #138 if the pool saturates rather than inflating any snapshot or raising the timeout.
4. Half-migrated incoherence: mid-transition some tiles are native (modern) and some still bounce to the
   legacy coffee tab, so the owner sees two looks in one session. Mitigation: the modern base and design
   land first so the home and every native page are coherent at once; cohort order claims whole tiles fast
   so the window where a tile still bounces to the legacy coffee page is short, and each cohort claims whole
   tiles, never half.
5. M3 record-sale is a build, not a port (no modal, no `addSale`, line-item payload, mutates stock).
   Mitigation: scoped as its own task against the real `SaleCreate` schema; any contract gap becomes a
   separate explicit endpoint task (A-Q12), never a silent change.
6. The chat-to-screen refresh contract (`beans:navigate` / `beans:refresh`) assumes one Alpine scope with
   four tabs; split across separate documents it breaks. Mitigation: re-establish the contract per page so a
   chat action refreshes the page it is on, and never claims to refresh a screen it cannot reach (AC8).

## Dependencies

- Reuses the existing `/api/tenants/{phone}/...` endpoints in products.py, stock.py, sales.py, expenses.py,
  and AnalyticsService. No endpoint changes.
- Reuses the registry + provider protocol (ARCHITECTURE.md D-020, D-023) and the home service fail-open
  fan-out (home_service.py).
- Reuses the Timonel chat widget (`/static/js/chat_widget.js`, `chat_widget.css`, factory `window.beansChat`).
- Interacts with the open performance debt eldaroo/beans-assistant#138; does not resolve it.
- Push and issues via the eldaroo gh token. Deploy via the existing `deploy.yml` workflow_dispatch and the
  per-node Docker path (no new migration: this spec adds no tables or columns).

## Cost-shaped considerations

- No new database objects, so no migration step and no data risk. The change is templates, one registry
  descriptor, four new route modules, one provider, and the two bases.
- Attention cost lands in the shared base extraction and the pixel gate; get that right once and the four
  CRUD pages are a repeated shape.
- The deploy is the existing manual flow to a live business, so it keeps the prod-deploy confirm gate.
