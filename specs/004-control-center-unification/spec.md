# Spec 004: Control Center as the single owner product

## Problem

Beans has two owner-facing surfaces that share the same tenant data and read as two
different products. The Control Center at `/home/{phone}` is a read-only launcher in
an indigo brand. The legacy page at `/tenants/{phone}` is the only place with real
write paths (product ABM, stock add and adjust, expenses add and delete, sale cancel)
and it wears a coffee brand and extends a different base template. Three of the seven
Control Center tiles (Resultado, Stock, Ventas) do not open their own page: they bounce
the owner back into the legacy page via `?tab=...`, crossing a brand boundary mid task
with a full document reload. The owner cannot tell where the product ends. Dario, after
landing on the legacy view from a link, said: "ese link me abre la vieja vista" and then
"no podemos separarlo completamente, ahora esta todo mezclado".

## Why now

M1 to M5 of the Control Center (spec 003) shipped and deployed on 2026-10-14. The home
renders all seven tiles live in about 0.9s. The read surface is done. The unification is
the next honest step: without it, every day the owner uses the product they cross the seam
the Control Center was meant to remove. The surface is live in production, so the cost of
the split is paid by a real business on every session.

## What this does

Make the Control Center the single owner-facing door. Every operation (products, stock,
sales, expenses, result) reads AND writes inside the Control Center, under one design (the
current modern Control Center look, indigo/Inter, kept by Dario's decision),
one held nav, one shared base template, with Timonel present on every page. The legacy
`/tenants/{phone}` page is not deleted or changed; it stays live, reachable only from Admin,
as a fallback. No owner-facing path lands on it.

## Scope

### In scope

- A shared owner-facing base template (`cc_base.html`) extracted from the current home,
  carrying the current modern Control Center design (indigo/Inter, kept per Dario's decision;
  the panel's coffee recommendation is overruled), the held nav rail, the theme toggle, and a
  Timonel chat slot.
- Re-basing the live home onto `cc_base.html` with no visible change (gated by a visual
  self-regression check, current home as golden).
- A new `productos` module (registry descriptor, tile, provider snapshot, dedicated page)
  with full product ABM reusing `products.py`.
- Dedicated Control Center pages for Stock, Ventas, and Resultado, each reusing the existing
  `/api/tenants/{phone}/...` endpoints, with the three tiles repointed off `?tab=...`.
- Wiring the two legacy gaps on the new Ventas page: record-sale (`POST /sales`, currently
  unwired) and view-sale-detail (`GET /sales/{id}`, currently an `alert` stub).
- Fixing the Resultado tile, which today points at the expenses tab (`?tab=expenses`).
- Migrating the four existing read-only module pages (costos, produccion, logistica,
  proveedores) onto `cc_base.html`, styling only, behind the visual check.
- Embedding Timonel once in the shared base so every page inherits it, and re-establishing
  the chat-to-screen refresh contract across separate documents.
- Removing every owner-facing link into `/tenants/{phone}` and verifying no owner route
  resolves to legacy.

### Out of scope

- Deleting or editing the legacy `/tenants/{phone}` page or its `base.html`. It stays the
  Admin-only fallback, unchanged.
- Any new or rewritten CRUD endpoint. New pages are surfaces over the existing APIs.
- A client component framework (React, Vue, a bundler). Pages are server-rendered plus Alpine.
- Changes to auth, multi-tenant scoping, the WhatsApp channel, or the chat widget internals.
- Richer provider snapshots that feed the tiles. Each snapshot stays one bounded query.
- The durable snapshot-pool performance fix. That is tracked at eldaroo/beans-assistant#138;
  this spec must not regress the home and must file against #138 if the pool saturates, but
  it does not resolve #138.
- Supplier login and WhatsApp check-ins (spec 003 M6/M7, human-gated). Untouched here.

## Whole-problem surface

```yaml
- id: S1-shell
  surface: One shared base (cc_base.html) in the current modern Control Center design that the home and every module page extends; held nav, theme toggle, Timonel slot; the live home re-based with no visible change.
- id: S2-productos
  surface: A new productos module (tile, route, provider snapshot) with a dedicated page doing full product ABM over products.py.
- id: S3-stock
  surface: A dedicated Stock page (table, add, signed-delta inline adjust, low-stock filter) over stock.py, tile repointed off the legacy tab.
- id: S4-ventas
  surface: A dedicated Ventas page (list, cancel, view-detail, and the newly wired record-sale) over sales.py, tile repointed.
- id: S5-resultado
  surface: A dedicated Resultado page (ingresos and ganancia plus expenses add and delete) over AnalyticsService and expenses.py, tile repointed, the Resultado-to-expenses mislabel fixed.
- id: S6-legacy-pages-migrated
  surface: The four existing read-only pages (costos, produccion, logistica, proveedores) re-based onto cc_base, styling only, behind the visual self-regression check.
- id: S7-timonel-everywhere
  surface: Timonel embedded once in cc_base so every owner page has it, with the chat-to-screen refresh contract re-established across separate documents.
- id: S8-demote-legacy
  surface: No owner-facing path reaches /tenants/{phone}; legacy reachable only from Admin; verified by a crawl of the owner routes.
```

## Acceptance criteria

1. `backend/templates/cc_base.html` exists and is extended by `control_center.html`; opening
   `/home/{phone}` as the owner renders the same tiles and attention strip as before, in the
   current modern Control Center design, and a visual self-regression check against the pre-change home passes (S1-shell).
2. The `productos` module is registered in `backend/modules/registry.py` with a tile labeled
   "Productos" and route `/productos/{phone}`; the home shows a Productos tile whose value is the
   active product count, degrading fail-open to a dash when its provider raises (S2-productos).
3. `GET /productos/{phone}` as the owner returns 200 and lists the tenant's products (SKU, nombre,
   descripción, costo, precio, estado); creating a product via the page issues `POST /api/tenants/{phone}/products`
   and the new row appears after refetch; editing issues `PUT /{id}`; deleting issues
   `DELETE /{id}` and the row leaves the active list (soft-deactivate, reusing products.py) (S2-productos).
4. `GET /stock/{phone}` as the owner returns 200 and lists stock; adding stock issues
   `POST /api/tenants/{phone}/stock/add`; an inline quantity edit issues `POST /stock/adjust` with the
   signed delta `newQty - currentQty` (not the typed absolute); the low-stock filter shows only rows at
   or below the threshold; the Stock tile route is `/stock/{phone}`, not `?tab=stock` (S3-stock).
5. `GET /ventas/{phone}` as the owner returns 200 and lists sales; canceling issues
   `DELETE /api/tenants/{phone}/sales/{id}`; a row's view-detail opens a modal populated from
   `GET /sales/{id}` (not an `alert`); recording a sale through a line-item modal issues `POST /sales`
   and the sale appears after refetch; the Ventas tile route is `/ventas/{phone}` (S4-ventas).
6. `GET /resultado/{phone}` as the owner returns 200 and shows ingresos and ganancia from the same
   AnalyticsService the caja provider reads, plus an expenses list where adding issues
   `POST /api/tenants/{phone}/expenses` and deleting issues `DELETE /{id}`; the caja/Resultado tile
   route points at `/resultado/{phone}` and the tile headline reads a result figure, not the expenses
   tab (S5-resultado).
7. `costos.html`, `produccion.html`, `logistica.html`, and `proveedores.html` each extend `cc_base.html`;
   each page still returns 200 with its existing data and the visual self-regression check against its
   pre-change render passes (S6-legacy-pages-migrated).
8. Timonel is mounted once through the chat slot in `cc_base.html`; it appears on the home and every
   module page; a chat action that changes data on the current page triggers that page's refetch (the
   re-established refresh contract), and a chat action does not silently claim to refresh a screen it
   cannot reach (S7-timonel-everywhere).
9. A crawl of the owner-facing routes (`/home/{phone}` and every tile route) finds no link, redirect,
   or `href_for` fallthrough that resolves to `/tenants/{phone}`; the empty-state card no longer links
   to the legacy base; `/tenants/{phone}` still returns 200 when reached directly from Admin (S8-demote-legacy).
10. After all of the above, `build_home` for a live tenant still renders all tiles within the snapshot
    deadline at production latency (near the current 0.9s, no new degraded tile from the eighth
    concurrent snapshot); if the shared pool saturates, a note is filed against eldaroo/beans-assistant#138
    rather than inflating any snapshot or raising the timeout (S2-productos, perf guard).

## Mockup

The owner-facing surface was designed before implementation via a 2-iteration mockup
deliberation with Kaze and Sally. The frozen mockup lives at `./mockups/index.html` and is
the visual contract any /develop run inherits.

- **Screens covered:** the Home (7 tiles + attention strip) and the exemplar new CRUD page,
  Productos. Stock, Ventas, and Resultado follow the same mold.
- **State machine:** empty (inviting CTA), loading (skeleton echoing the table), populated (1,
  50, and 5000 rows), error (server 500 with Reintentar, validation 4xx inline, 403 read-only).
- **Brand:** the modern Control Center design (indigo/Inter), kept per Dario's decision. The
  panel's coffee recommendation was overruled.
- **Iterations:** 2 - see `./mockups/iterations.md`.
- **Approved on:** 2026-10-15.
- **Design panelists:** Kaze, Sally.

## Open questions

- A-Q10: Migrate the four read-only pages in one styling-only cohort, or alongside each CRUD page as
  it is built? Right person: panel default. Default to proceed: one styling-only cohort right after the
  base extraction so the brand converges before CRUD work (Winston, Amelia agree on the cohort; they
  differ only on how early, resolved by the pixel gate making an early migration safe).
- A-Q11: Does the eighth concurrent snapshot (productos) fit the shared pool within the deadline at
  live latency, or must #138 land first? Right person: measured, not argued. Default to proceed: ship
  the shell and Productos with a bounded count and measure on the live cluster; resolve #138 before the
  later repoints only if the pool saturates.
- A-Q12: Does record-sale reuse the existing `POST /sales` shape, or does the missing modal need a
  payload the endpoint lacks? Right person: the dev building Ventas, against the real `SaleCreate` schema.
  Default to proceed: build against the existing contract; treat any gap as a separate, explicit endpoint
  task, not a silent change.

## Panelists who contributed

- Winston (BuildOS Architect) — the architecture: one shared base extracted from the home, CRUD as Alpine
  over the existing endpoints, registry-driven routing, the eighth-snapshot perf guard. Authored the
  ARCHITECTURE.md delta (D-024 to D-028).
- Amelia (BuildOS dev) — feasibility: record-sale is a build not a port, the signed-delta stock trap, the
  Tailwind-to-plain-CSS port asymmetry, and the chat refresh contract breaking across documents.
- Bob (Scrum Master) — sequencing: shell first, the cohort grouping that keeps the live product coherent
  at every stop, and the half-migrated incoherence risk living in the order, not the code.
- Kaze (creative direction) — the bounce is the mixing (clicking a tile crosses a brand boundary with a
  full document reload); presence on the real numbers, inviting empty states, the held nav and soft
  transition. Kaze recommended coffee/cream as the single brand; Dario overruled and chose to keep the
  current modern Control Center design, so the unification adopts the modern look, not coffee.
