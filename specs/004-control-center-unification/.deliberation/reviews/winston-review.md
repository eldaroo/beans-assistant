# Winston review: Control Center as the single product

## 1. What problem is this actually solving

Not styling. Surface ownership. There is no single owner-facing door that both reads and writes. The Control Center reads, then bounces three tiles to a different document that writes, wears a different brand, and is reachable only through Admin. The owner meets two half-products. The fix is one surface that owns both the read and the write for every operation.

## 2. Smallest first version that proves the idea

Extract the shared base from the home, then build Productos as the first CRUD-on-Control-Center page on it. One page exercises the whole stack: shared base, Alpine over the existing JSON endpoints, a registry descriptor, a bounded provider snapshot. If Productos reads, writes, and renders in the Control Center brand without regressing the home, every later page repeats the shape. The three bounced tiles stay bounced until the pattern is proven.

## 3. Three risks that would kill this if ignored

1. Re-basing the deployed home silently regresses it. Extracting a base and re-pointing the live home can shift spacing or color by a pixel no one notices until Dario does. Gate the re-base with the pixel self-regression check, home as golden.
2. CRUD pages drift from the reused endpoint contracts, or double-write. The endpoints carry invariants (soft-delete, signed stock delta, cancel-not-destroy). A page that reimplements any of that, or mutates local state and the server separately, corrupts the ledger.
3. The eighth concurrent snapshot pushes the home past its deadline. Productos adds a provider to a fan-out already strained by live cross-container latency (the #138 debt). If the snapshot does real work instead of one count, the 0.9s render degrades for everyone.

## 4. What success looks like at 90 days

No owner-facing path lands on `/tenants/{phone}`. Every operation (products, stock, sales, expenses, result) reads and writes inside the Control Center under one brand, one nav, one base. Legacy is unchanged, Admin-only, a fallback. Timonel is present on every Control Center page. The home still renders near 0.9s with all tiles live, and the Resultado tile points at result, not at the expenses tab.

## 5. Atomic tasks (each <= 1 day)

- T1. Extract `cc_base.html` from `control_center.html` (indigo/Inter, Alpine, theme toggle, chat slot). Re-point the home to it. Prove pixel-equal via the self-regression gate.
- T2. Migrate the four existing read-only module pages to extend `cc_base`. Styling only, no logic change.
- T3. Add the `productos` registry descriptor and provider snapshot (active product count, one COUNT query, fail-open).
- T4. Build `/productos/{phone}`: `_build_view` plus an Alpine factory over `products.py` (list/add/edit/soft-delete).
- T5. Build `/stock/{phone}`: `_build_view` plus Alpine over `stock.py` (add, inline adjust, low-stock filter). Repoint the stock tile.
- T6. Build `/ventas/{phone}`: list, cancel, view-detail via `GET /sales/{id}`, and wire record-sale via `POST /sales`. Repoint the ventas tile.
- T7. Build `/resultado/{phone}`: ingresos/ganancia plus expenses add/delete. Repoint the caja tile and fix the Resultado-to-expenses mislabel.
- T8. Embed the Timonel widget partial into `cc_base` so every Control Center page has chat.
- T9. Remove every owner-facing link into `/tenants/{phone}`. Verify no owner path reaches legacy.
- T10. Perf check: confirm the home renders under the deadline with eight concurrent snapshots at live latency. File against #138 if the pool saturates.

## 6. The one thing only my faculty would have noticed

The proposed cohort order is wrong, and it is the most expensive mistake available. Unified design is listed last (M6). Build the four CRUD pages standalone in M1 to M4 and extract the base in M6, and you write every page twice: once standalone, once re-based. The base extraction is the foundation seam, not the finish; it must come first, so every page is born extending it. Second, smaller but real: the Resultado tile points at the expenses tab (`?tab=expenses`), so M4 is a correctness fix wearing the costume of a move, and its check must assert the result data, not just the new route.
