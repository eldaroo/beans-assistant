# Bob review — Control Center unification (sequencing lens)

## 1. What problem is this actually solving

Two doors to one business. The owner lands on the legacy coffee page by accident, and the real CRUD lives there while the Control Center is a read-only launcher that bounces three tiles back to legacy. The problem is not missing features. It is a split surface where the nice door is hollow and the working door is hidden. We are closing that split so one door owns the whole job.

## 2. Smallest first version that proves the idea

One tile that no longer bounces. Ship M1 Productos: a dedicated `/productos/{phone}` page with full ABM over the existing products.py, plus its registry tile. The moment one owner-facing tile does real CRUD inside the Control Center shell and never touches `/tenants/{phone}`, the pattern is proven and copyable. Everything after M1 is the same move repeated.

## 3. Three risks that would kill this

- Half-migrated incoherence. Mid-transition, some tiles do new CRUD and some still bounce to the coffee-brand legacy tab. The owner sees two visual worlds in one session. This is the central risk and it lives in the sequencing, not the code.
- Shared snapshot pool regression. Each new provider snapshot widens the fan-out under the 10s deadline (#138 debt). Add Productos plus three more snapshots and the ~0.9s home render degrades sprint by sprint, invisibly, until it crosses the deadline.
- Endpoint reuse drift. The spec says reuse, never rewrite. Under time pressure a page author re-implements a stock adjust or a cancel-sale path, and now two code paths mutate the same tenant schema.

## 4. Success at 90 days

No owner-facing path reaches `/tenants/{phone}`. All four operational tiles plus Productos do their CRUD inside the Control Center. Timonel is reachable from the Center. One brand, one nav. Home render still under 1s. Legacy still live, reachable only from Admin, as the fallback it was promised to be.

## 5. Atomic tasks (dependency-ordered, each <=1 day)

1. Add `productos` module to registry (tile + route stub).
2. Build `/productos/{phone}` page: list + add + edit + soft-delete over products.py.
3. Add productos provider snapshot (active count), verify fan-out stays under deadline.
4. Build `/stock/{phone}` page (table + add + inline adjust + low-stock filter); repoint stock tile.
5. Build `/ventas/{phone}` page (list + cancel + view-detail via GET /sales/{id}).
6. Wire the unwired record-sale (POST /sales) into the ventas page.
7. Repoint ventas tile off `?tab=sales`.
8. Build `/resultado/{phone}` page (ingresos/ganancia + expenses add/delete).
9. Repoint caja/Resultado tile and fix the Resultado-points-at-expenses mislabel.
10. Extract one shared Control Center shell (nav, theme tokens) from control_center.html.
11. Reskin the four module pages and the new pages onto the shared shell.
12. Embed Timonel chat widget into the shared shell.
13. Remove every owner-facing link into `/tenants/{phone}` (empty-state card, href_for fallthrough).
14. Verify: crawl Control Center, assert no owner route resolves to legacy; confirm home render under 1s.

## 6. The one thing only my faculty noticed

The M6 sequencing fork. Build the shared shell FIRST, as task 10's output promoted to task 2, so every page is born on one brand. Do not leave unification LAST. A retheme at the end is a second full pass over five pages and the exact window where half-migrated incoherence is worst and longest. Define the shell shim early (it can start as control_center.html's own CSS), then each page cohort ships already coherent. Cohorts: A = tasks 1 to 3 (Productos, proves pattern on the shell). B = 4 to 7 (Stock, Ventas). C = 8 to 9 (Resultado, every tile now native). D = 10 to 14 (shell hardening, Timonel, demote, verify). Each cohort is live-verifiable alone and leaves no tile bouncing that a prior cohort already claimed.
