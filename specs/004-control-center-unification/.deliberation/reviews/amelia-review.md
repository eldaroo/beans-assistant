# Amelia (dev) review — Control Center unification

Dev lens, grounded in file:line reads of the legacy page and the five endpoints.

## 1. What problem is this actually solving?

One owner-facing door. Today the only real CRUD lives on the legacy coffee-brand `/tenants/{phone}` page; the Control Center is a read-only launcher whose Resultado/Stock/Ventas tiles bounce the owner straight back into that old page. The work moves CRUD onto dedicated Control Center pages so no owner path lands on the legacy view.

## 2. Smallest first version that proves the idea

M1 Productos as a vertical slice: one dedicated `/productos/{phone}` page with the full product list, add/edit, and deactivate, plus its registry tile and provider count. It proves the whole pattern end to end (new surface, reused endpoint, CC styling, tile wiring) on the one domain that has no sale-side complexity.

## 3. Three risks that would kill this

- M3 record-sale is a build, not a port. The legacy page has `showAddSaleModal` state but no modal markup, no `saleForm`, and no `addSale()` (`tenant_detail.html`). It was never wired because POST `/sales` needs a line-item payload and mutates stock (cancel restores stock, `sales.py:102`). Scoping it as "wire the gap" undersells it.
- M6 shared-base extraction on live pages. costos/produccion/logistica/proveedores are each a full standalone document duplicating the same `:root` tokens (`costos.html:11`). Extracting one base and retrofitting four deployed pages is a refactor with real regression surface. Do it last, behind pixel characterization, never first.
- Snapshot pool regression. Adding the Productos provider is an 8th concurrent snapshot under the shared 10s deadline (#138). Keep the CRUD pages client-fetch (shell renders instant, Alpine fetches), never server-side `_build_view`, so they stay off the pool.

## 4. Success at 90 days

An owner reaching the base URL lands only in the Control Center, does every daily task (products, stock, sales incl. recording one, resultado with expenses) from dedicated pages under one brand and nav with Timonel present, and `/tenants/{phone}` is reachable only from Admin. Home render stays near 0.9s.

## 5. Atomic tasks (each <= 1 day)

1. M1: add `productos` module to `registry.py` (tile, `/productos/{phone}`, provider = active product count).
2. M1: build `productos.html` client-fetch shell; port product table + add/edit modal + deactivate, re-expressed in CC tokens.
3. Cross: extract the four `loadX/saveX/deleteX` fetch methods into one shared static JS CRUD factory reused by every page.
4. M2: build `/stock/{phone}`; port table + add modal + inline adjust, keeping the signed-delta conversion; repoint stock tile.
5. M3: read `SaleCreate` schema; build the record-sale modal (line items, qty, customer) against POST `/sales`.
6. M3: build view-detail modal from GET `/sales/{id}` (replace the `alert(JSON)` stub); port cancel; repoint ventas tile.
7. M4: build `/resultado/{phone}` (ingresos/ganancia + expenses add/delete); repoint tile; fix the Resultado->expenses mislabel.
8. M5: load `chat_widget.js`/`.css` into the CC shell and pages; instantiate `beansChat` per page.
9. M5: re-establish the `beans:navigate`/`beans:refresh` refresh contract across separate pages (see prompt 6).
10. M6: extract one shared base (shell, tokens, theme script, nav) for CC and its pages.
11. M6: migrate the four standalone module pages onto the base behind pixel characterization tests.
12. M7: remove every owner-facing link into `/tenants/{phone}`; confirm auth routes owner to `/home` only.

## 6. The one thing only my faculty noticed

The legacy `init()` wires `beans:navigate` and `beans:refresh` so a chat action refreshes the current tab (`tenant_detail.html:1045-1066`). That contract assumes one Alpine scope with four tabs. Split across separate dedicated pages, a chat action on Ventas cannot refresh Stock, because each page is its own document with its own scope. M5 is not just "embed the widget"; the chat-to-screen refresh contract silently breaks and must be redesigned per page. Also note the port asymmetry: the JS methods port verbatim, but every Tailwind class and `--color-*` token must be rewritten into the CC plain-CSS vocabulary, and stock adjust takes a signed delta while the UI shows an absolute, so the `newQty - currentQty` conversion must survive the port.
