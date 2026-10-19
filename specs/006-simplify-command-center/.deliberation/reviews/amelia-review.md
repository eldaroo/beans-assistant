# Amelia (Developer) review — Simplify the Command Center

## 1. What problem is this actually solving?

One non-technical owner has nine full-page surfaces to run a small business, each with its own Alpine CRUD factory. Timonel can already write sales, stock, products and expenses and read analytics over `/api/tenants/{phone}/chat`. So the real job is not "fewer modules." It is "one place to act, numbers visible, mostly by talking." The nine-entry rail in `registry.py` plus `nav.owner_rail` is navigation overhead the owner pays on every task Timonel could do in one sentence.

## 2. Smallest first version that proves the idea

Reuse `cc_base.html`. Do not build a second shell. Two concrete changes:

- Add a `tab` field to `Module` in `modules/protocol.py`, set it on each descriptor in `registry.py`, and add `nav.owner_tabs()` returning at most four tabs: Hoy, Operación (resultado, productos, stock, ventas), Costos y producción (costos, produccion, logistica, proveedores), and keep Hoy as home. Render these four in the `.rail` block of `cc_base.html` (lines 124-133) instead of the flat module list. This is a nav-only change: the eight existing pages stay untouched behind their tab.
- Promote Timonel on Hoy from the corner `_timonel_slot.html` to the main content column of `control_center.html`, tiles becoming drill-downs beneath it.

The existing Alpine pages stay standalone pages for v1. Merging four factories into one page per tab (include each `{% block content %}` as a partial, concatenate the `body_scripts`) is the follow-on, not v1. Alpine supports multiple independent `x-data` islands on one page, so the merge is mechanical later, but it multiplies seed queries on first paint.

## 3. Three risks that would kill this

- **Chat state dies on every navigation.** `chat_widget.js` initializes `messages: []` on load and persists only dock and greeting flags in localStorage, never the thread. Full-page tab switches and `beans:navigate` (which does `window.location.href`) wipe the visible conversation. If Timonel is primary, this is fatal.
- **Alpine state collision on merged pages.** Four factories on one page share one DOM. Any global selector, duplicate element id (several pages use `modal-title`), or shared `localStorage` key will cross-contaminate.
- **Trust in AI writes to money.** Timonel writing sales and expenses with no visible confirmation receipt erodes trust the first time a number looks wrong.

## 4. Success at 90 days

Owner runs a normal week from Hoy, mostly by talking. Rail is four tabs. Most writes originate in Timonel; module pages are opened to verify, not to input. Chat conversation survives tab switches. No regression in the eight CRUD endpoints.

## 5. Atomic tasks (each <= 1 day)

1. Add `tab` field to `Module` in `modules/protocol.py`; set it on all eight descriptors in `registry.py`.
2. Add `nav.owner_tabs()` returning <= 4 tabs; keep `owner_rail` until cutover.
3. Render four tabs in `cc_base.html` rail block; pass `active_tab` from each route.
4. Persist chat thread to sessionStorage keyed by phone in `chat_widget.js`; rehydrate on load.
5. Rehydrate from server thread (specs/001 memory) as fallback when sessionStorage is empty.
6. Move Timonel to main column of `control_center.html`; tiles become drill-downs.
7. Verify `beans:navigate` targets resolve to the new tab routes.
8. Dedup element ids across the four Operación pages before any merge.
9. Add a visible write-receipt bubble after each Timonel DB write.
10. Mobile: verify four tabs fit the stacked nav under 400px.
11. Regression-test the eight module pages render unchanged under the new rail.

## 6. The one thing only a developer notices

The visible chat is ephemeral. `messages: []` resets on every full-page load; only the server remembers the thread. Make Timonel primary without client rehydration and the owner loses their conversation every single time they open a tab.
