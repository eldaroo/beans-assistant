---
spec: control-center-unification
mode: update
author: Winston (BuildOS Architect)
appends_after: D-023
note: Append-only delta. Quinn renumbers to the next D-XXX after the existing log.
---

# Control Center unification addendum (spec 004)

Dario made the Control Center the single owner-facing product. All CRUD moves off the legacy `/tenants/{phone}` page onto dedicated Control Center pages; legacy stays live, Admin-only, a fallback. These decisions govern how one design system and real write paths arrive without regressing the deployed home. They build on D-020 (registry plus provider protocol) and D-023 (existing surfaces as modules).

## Decision log (delta)

### D-024: One owner-facing base, extracted from the home; legacy base untouched; extraction is foundational

- **Chosen.** Extract a shared Jinja base `cc_base.html` from the current `control_center.html` (indigo/Inter, Alpine, theme toggle, chat slot). The home and every module page, read-only and new CRUD, extend it. Legacy `base.html` (coffee) is left exactly as is under Admin. The extraction is the first cohort, before any new CRUD page.
- **Alternatives.** (a) A shared CSS or partial include across the standalone pages. (b) Leave pages standalone, theme-match by hand. (c) Migrate the legacy page onto the new base too.
- **Why this won.** Duplication across standalone documents is the debt; one base is the single place brand and nav change. Extracting from the already-indigo home re-bases it to a byte-equal surface, not a redesign, so the deployed look is preserved by construction and proven by the pixel self-regression gate (home as golden). First means each new page is born extending the base, written once.
- **Why the alternatives lost.** (a) A CSS include still leaves each page re-declaring doctype, head, nav, and theme, so nav drift persists. (b) Hand theme-matching is the status quo that produced the mixed surfaces. (c) Touching the legacy base risks the Admin fallback for zero owner gain.
- **Implications.** Two bases: `cc_base.html` (owner) and legacy `base.html` (Admin). The four existing pages migrate in a styling-only cohort. Building the base last (the proposed M6) rewrites all four CRUD pages twice; this reorders design to the front.
- **Panel source.** Winston, with Sally on preserving the shipped home and Kaze on one brand, one nav.

### D-025: CRUD pages are Alpine over the existing JSON endpoints; three read layers stay distinct

- **Chosen.** Each new page server-renders its initial read through the route `_build_view` (fast paint, tenant-scoped, `no-store`, fail-open) and hydrates one Alpine factory per page, mirroring the legacy `tenantDashboard`, that owns every mutation by calling the existing `/api/tenants/{phone}/...` endpoints then refetching. Three read surfaces keep separate jobs: provider `snapshot()` is the home tile number, route `_build_view` is the page initial render, `/api` endpoints are the Alpine CRUD path.
- **Alternatives.** (a) A client framework (React/SPA). (b) Server-side form posts with full reloads. (c) Fold page detail into the provider snapshot so tile and page share one fetch.
- **Why this won.** Alpine is already loaded and the legacy page already writes through this exact factory against these exact endpoints, so no new toolchain, no build step, and the reuse constraint is honored by construction. The three-layer split keeps each path at its own cost and failure mode.
- **Why the alternatives lost.** (a) A framework adds a bundler and breaks D-020's server-rendered-descriptor convention. (b) Full reloads lose the inline stock-adjust interaction and fight the no-store model. (c) A shared fetch makes the home pay the page's full query, the regression D-027 guards.
- **Implications.** One Alpine factory per page template. Endpoints are never rewritten. The two legacy gaps (unwired record-sale, alert-stub view-detail) are wired on the new Ventas page against the present `POST /sales` and `GET /sales/{id}`.
- **Panel source.** Winston, with Amelia on reusing the endpoint contracts verbatim.

### D-026: Routing stays registry-driven; productos is a new descriptor; tile repoints are registry edits

- **Chosen.** Every new or repointed surface is a change to `backend/modules/registry.py` plus a route, never a home-template edit (preserves D-020 and the Control Center AC1). `href_for` already treats a `/`-prefixed route as absolute, so repointing a bounced tile is a one-line change from `?tab=x` to `/{module}/{phone}`. `productos` is a new descriptor (tile, route, provider, page). The Resultado-to-expenses mislabel and the `?tab=expenses` base pointer are fixed when the caja/Resultado tile repoints.
- **Alternatives.** (a) Hard-code the new tiles and routes in the home template. (b) Keep a query-param tab router for the new pages.
- **Why this won.** The registry is already the single source of module truth; repointing through it keeps the home untouched and the invariant intact. Dedicated `/{module}/{phone}` routes replace the `?tab=` bounce to legacy.
- **Why the alternatives lost.** (a) Couples the home to every module, the coupling D-020 forbids. (b) The tab router is the mechanism that bounces to legacy; keeping it reintroduces the problem.
- **Implications.** Five registry touches: one add (productos), three repoints (stock, ventas, caja/Resultado), one label fix. No home-template edit.
- **Panel source.** Winston.

### D-027: Provider snapshots stay one bounded query; productos is the eighth concurrent snapshot

- **Chosen.** The productos provider does one bounded query (active product count) and fails open to a degraded tile, per D-020 and D-021. Page detail lives only in the route `_build_view`, never in the snapshot.
- **Alternatives.** (a) A richer productos snapshot feeding the tile. (b) Raise `SNAPSHOT_TIMEOUT_S` again.
- **Why this won.** The fan-out is concurrent, so one more bounded query does not serialize, but it is one more connection on the shared pool under the 10s deadline and the live latency. One count bounds the home's growth to one cheap query per module and protects the 0.9s render.
- **Why the alternatives lost.** (a) A richer snapshot makes the home pay page-weight for a tile. (b) Raising the timeout hides pool saturation and degrades felt speed.
- **Implications.** Productos is the eighth concurrent snapshot. Before M1 ships, confirm the pool serves eight concurrent bounded queries within the deadline at live latency; if it saturates, that fan-out is what #138 must fix (a combined per-module aggregate, per A-Q9), not a reason to inflate any snapshot.
- **Panel source.** Winston, grounded in the #138 perf debt.

### D-028: Timonel is embedded once in the shared base, not per page

- **Chosen.** The chat widget (`chat_widget.js` factory `window.beansChat`, `chat_widget.css`) mounts through a chat slot in `cc_base.html`, so every Control Center page inherits Timonel from the base.
- **Alternatives.** (a) Include the widget on each page. (b) A dedicated `/chat` page only.
- **Why this won.** Chat is a shell concern; one mount gives every owner surface the assistant without the legacy page, and the asset loads once.
- **Why the alternatives lost.** (a) Per-page includes duplicate the mount and drift. (b) A chat-only page splits the assistant off the surfaces it should assist.
- **Panel source.** Winston, with Kaze on presence on every owner surface.

## Conventions (implementing agents follow these)

- New pages extend `cc_base.html`. Never add a third owner-facing base.
- One Alpine factory per page template (`productosDashboard`, `stockDashboard`), mirroring legacy `tenantDashboard`.
- Writes go only through the existing `/api/tenants/{phone}/...` endpoints. No endpoint rewritten, no second write path.
- Provider `snapshot()` is one bounded query and fails open. Page detail belongs in the route `_build_view`.
- Tile wiring is a registry change, never a home edit. Re-basing the home is gated by the pixel self-regression check, current home as golden.

## Non-goals

- No deletion or edit of the legacy page or its `base.html`; it stays the Admin-only fallback.
- No client component framework; pages are server-rendered plus Alpine.
- No new CRUD endpoints; new pages are surfaces over existing APIs.
- No change to auth, multi-tenant scoping, channels, or chat widget internals.
- No richer provider snapshots to feed tiles.

## Open architectural questions

- **A-Q10.** Migrate the four read-only pages in one cohort or alongside each CRUD page? Fallback: one styling-only cohort right after the base extraction, so the brand converges before CRUD work.
- **A-Q11.** Does the eighth concurrent snapshot fit the pool within the deadline at live latency, or must #138 land first? Fallback: ship M1 with the bounded count and measure; resolve #138 before the later repoints only if saturated.
- **A-Q12.** Record-sale on the new Ventas page: reuse the existing `POST /sales` shape, or does the missing modal need a contract the endpoint lacks? Fallback: build against the existing contract; treat any gap as a separate endpoint task.
