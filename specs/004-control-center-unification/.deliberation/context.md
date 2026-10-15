# Context packet — Control Center as the single product (beans-assistant)

Run-id: control-center-unification-20261014-155348
Target: clients/eldaroo/beans-assistant (target_kind = existing)
Host repo for issues: eldaroo/beans-assistant (push + issues via the eldaroo gh token)
Primary domain: BuildOS. User-facing surface: YES (kaze_attach = true). Architecture: UPDATE mode (ARCHITECTURE.md exists, Timonel-scoped; this spec appends Control Center decisions).

Each panelist writes against THIS packet, in their own voice, in their own review file. Answer the same six prompts.

## Raw idea (verbatim, from Dario via Quinn)

Beans has TWO mixed surfaces today:

1. Legacy tenant page `/tenants/{phone}` (`backend/templates/tenant_detail.html`, extends `base.html`, coffee/cream brand). This is the ONLY place with real CRUD: product ABM (`backend/api/products.py`), stock add/adjust (`stock.py`), expenses add/delete (`expenses.py`), cancel sale (`sales.py`), delete tenant (`tenants.py`). It also embeds the Timonel chat widget (`/static/js/chat_widget.js` + `chat_widget.css`).

2. Control Center `/home/{phone}` (`backend/templates/control_center.html`, standalone indigo/Inter document, does NOT extend base.html). A read-only launcher. Of its 7 tiles, Resultado/Stock/Ventas BOUNCE back to `/tenants/{phone}?tab=...` via the `href_for` macro (base = `/tenants/{phone}`); costos/produccion/logistica/proveedores have their own read-only pages (`_build_view` server-side, no browser CRUD). The providers in `backend/modules/providers/` expose only `snapshot()`, no detail layer.

Dario opened the base URL, got routed through login into Admin, clicked a tenant, and landed on the OLD view. He said: "ese link me abre la vieja vista" then "no podemos separarlo completamente? ahora esta todo mezclado".

## Decisions already made by Dario (confirmed, not open)

- **One product.** The Control Center is the single owner-facing door. All CRUD from the legacy page moves into dedicated Control Center pages. The legacy `/tenants/{phone}` page is NOT deleted: it stays live and unchanged, reachable only from Admin, as a fallback. No owner-facing path lands on it.
- **Productos gets its own tile + dedicated page** in the Control Center, at the same level as Stock/Ventas/Costos.

These two are settled. Do not re-open them. Pressure-test everything else.

## Grounded inventory (from a read-only code survey, file:line verified)

Legacy `tenant_detail.html` (extends base.html):
- Tabs: Productos / Stock / Ventas / Gastos. `?tab=` query opens the matching tab.
- CRUD endpoints already exist and must be REUSED, never rewritten:
  - Products: GET `/api/tenants/{phone}/products`, GET `/{id}`, POST, PUT `/{id}`, DELETE `/{id}` (soft-deactivate). (`products.py`)
  - Stock: GET `/api/tenants/{phone}/stock`, POST `/stock/add`, POST `/stock/adjust` (signed delta). (`stock.py`)
  - Expenses: GET `/api/tenants/{phone}/expenses`, POST, DELETE `/{id}`. (`expenses.py`)
  - Sales: GET `/api/tenants/{phone}/sales`, GET `/{id}`, POST (create), DELETE `/{id}` (cancel). (`sales.py`)
  - Stats: GET `/api/tenants/{phone}/stats`.
- Two legacy gaps worth noting: record-sale is UNWIRED (modal/markup/function missing though `POST /sales` exists); view-sale-detail is an `alert(JSON)` stub (though `GET /sales/{id}` exists).
- Timonel chat: inline in `tenant_detail.html`, Alpine factory `window.beansChat` from `/static/js/chat_widget.js`; `chat_widget.css` loaded via base.html.

Control Center `/home/{phone}`:
- `control_center.html` is a full standalone `<!doctype html>` document, own CSS/theme (Inter/JetBrains Mono, indigo `#4F46E5`, localStorage `beans_cc_theme`). Does NOT extend base.html. No chat.
- `href_for` macro: route starting with `/` is absolute (`{phone}` substituted); otherwise appended to base `/tenants/{phone}` (so `?tab=...` bounces to legacy).
- Registry (`backend/modules/registry.py`): 7 modules, all `rail_group="Operación"`: caja/Resultado (`?tab=expenses` — mislabel: Resultado points at the EXPENSES tab), stock (`?tab=stock`), ventas (`?tab=sales`), costos (`/costos/{phone}`), produccion (`/produccion/{phone}`), logistica (`/logistica/{phone}`), proveedores (`/proveedores/{phone}`).
- `build_home` fans out all module snapshots concurrently on a shared ThreadPool under one deadline (SNAPSHOT_TIMEOUT_S currently 10.0s, raised from 3.0 for the live cross-container latency; durable perf fix tracked at eldaroo/beans-assistant#138). New pages must respect the fail-open/degraded pattern.

Dedicated module pages (costos/produccion/logistica/proveedores .html): all read-only server-rendered dashboards, standalone documents (not base.html), zero browser CRUD/XHR; data built in each route's `_build_view()` off-loop via `asyncio.to_thread` inside `tenant_scope(phone)`, `Cache-Control: no-store`. Providers expose `snapshot` + a pure `compute_snapshot` helper; NO detail layer — detail lives in the route `_build_view`s.

Auth: `require_tenant_match` gates owner (own phone only) + admin (bypass) + internal-token (bypass). Root `/` routes admin→`/admin`, owner→`/home/{phone}`.

## Constraints (hard)

- Multi-tenant, schema-per-tenant (`tenant_context`/`tenant_scope`, `PYTHONPATH=/app` inside the container). Already DEPLOYED in prod: https://beans-assistant.mdlautomations.duckdns.org
- REUSE existing endpoints; do not rewrite them. New pages are new SURFACES over existing APIs.
- New pages respect the home's fail-open/degraded pattern and the live cross-container DB latency (do not regress the ~0.9s home render; watch the shared snapshot pool and the #138 perf debt).
- Voice: no em-dashes, no en-dashes, no hype, no emojis, no exclamation marks, plain English.

## Proposed milestone cohorts (pressure-test these, reorder if needed)

- M1 Productos: new `productos` module in registry (tile + `/productos/{phone}` page) with full ABM (list/add/edit/soft-delete/bulk) reusing products.py; provider snapshot (active product count).
- M2 Stock: dedicated `/stock/{phone}` page (table + add + inline qty adjust + low-stock filter) reusing stock.py; repoint stock tile from `?tab=stock`.
- M3 Ventas: dedicated `/ventas/{phone}` page (list + cancel + view-detail modal using GET /sales/{id}) AND wire the missing record-sale (POST /sales); repoint ventas tile.
- M4 Resultado: dedicated `/resultado/{phone}` page (ingresos/ganancia via AnalyticsService/caja_module + expenses add/delete via expenses.py); repoint caja/Resultado tile; fix the Resultado→expenses mislabel.
- M5 Timonel in Control Center: embed the chat widget into the Control Center shell + pages so the owner has Timonel without the legacy page.
- M6 Unified design: extract ONE shared shell/base for Control Center + its pages (today control_center.html is standalone indigo, the 4 module pages are each standalone, legacy is base.html coffee). One brand, one nav.
- M7 Demote legacy: remove every owner-facing link into `/tenants/{phone}` (e.g. the empty-state card linking to base). Legacy reachable only from /admin.

## The six prompts (answer all six, <=600 words total)

1. What problem is this actually solving?
2. What is the smallest first version that proves the idea?
3. What 3 risks would kill this if ignored?
4. What does success look like at 90 days?
5. What atomic tasks does this break into? (list 5-15, each <=1 day)
6. What is the one thing only your faculty would have noticed?
