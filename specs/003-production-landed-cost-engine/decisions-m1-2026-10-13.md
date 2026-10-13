# M1 build decisions — Beans Control Center shell + status home

Run: `beans-control-center-20261013-113520` (/develop --headless, cohort-cut to M1 per genesis-build Section J).
Date: 2026-10-13. These are defensible defaults taken under the /develop autonomy authorization, plus the council's recorded deferral notes. Each is reversible and disclosed.

## Scope

Cohort = M1 only (surfaces S1 shell + S2 status home), children #108-114 / AC1-AC5. The spec has 25 children across 7 milestones; a single session cannot honestly verify ~25 of varied shape, so this run drained M1 end to end. M2-M5 append their own modules to the registry in later runs; M6/M7 stay behind their named-human gates.

## Decisions

- **D-M1-1 — Owner landing flips to `/home/{phone}`.** The owner `/` redirect now lands on the Control Center status home instead of `/tenants/{phone}`. The prior dashboard stays registered and reachable at `/tenants/{phone}` and is one click from every tile/attention item/rail entry (AC5). The change is three additive lines in `app.py` and one-line reversible.

- **D-M1-2 — The cash tile is labelled "Resultado", not "Caja/cash".** The platform has no bank/till ledger, so there is no true cash-on-hand figure in M1. The tile reports `profit_summary` = lifetime paid sales minus lifetime expenses, labelled as the accumulated result with the caption "acumulado · ventas pagadas menos gastos". A real period cash / runway figure (and any cash-low attention signal) waits on a cash ledger. (Council: Compass flagged the original "Caja = cash" as a metric overclaim; corrected.)

- **D-M1-3 — Stock shows units on hand + a uniform low-stock threshold; the "weeks of coffee" metric is deferred to M3.** A weeks-of-cover figure needs a consumption rate the platform does not store until the production module (M3) lands. M1 uses the data it has: total units and a low-stock signal when a product is at/below `LOW_STOCK_THRESHOLD` (20 units; HIGH at/below a quarter of it). The threshold is uniform across SKUs in M1; a velocity-aware, per-product threshold surfaced as a setting is the OQ4 follow-up (tracked, not shipped as "sensible"). Wording stays units ("quedan {qty} u"), never a faked weeks figure.

- **D-M1-4 — No trend direction arrow in M1.** No module computes a period-over-period delta, so the tile trend renders as a state colour (plus a `●` dot for `warn`) with NO `▲/▼` direction glyph. A real delta-driven arrow can come when a prior-period comparison is computed. (Council: Compass flagged the original `▲` as a fabricated up-trend; corrected.)

- **D-M1-5 — Drill-down routes to the existing dashboard tab.** Dedicated per-module pages do not exist in M1, so each module's `route` is a dashboard tab suffix (`?tab=stock|sales|expenses`); `tenant_detail.html` init() reads `?tab=` and opens that tab. "Reponer" lands on the stock tab. Dedicated module pages replace these routes as each module milestone ships.

- **D-M1-6 — Empty vs degraded is explicit.** Providers emit `STATUS_EMPTY` for a genuine no-data tenant (no products / no sales / net zero), distinct from a real zero. The home's `is_empty` is true only when every tile is empty AND none degraded, so a fresh tenant sees the onboarding welcome and an all-degraded home (e.g. DB down) renders its "—/no disponible" tiles so the outage is visible — never a false "load your data" welcome on a backend failure. (Council: Amelia + Kaze flagged the original inverted `is_empty`; corrected.)

- **D-M1-7 — One snapshot per module.** The provider protocol is a single `snapshot(phone) -> ModuleSnapshot(headline, attention)`; each module opens one tenant scope and fetches once, and the home service fans the result into the tile and the strip. The home service runs each snapshot in a worker thread with a 3s timeout (slow or broken => degraded tile) and the route builds off the event loop. (Council: Winston flagged the original two-provider double-fetch and the missing slow-path fail-open; corrected before M2 could inherit it.)

## Verification note

The `bin/qie develop` gate is Node/TS only and cannot classify a Python/FastAPI repo (it SKIPs tsc/lint on "no tsconfig/package.json"). The authoritative verification is the repo pytest suite: 19 M1 tests green + 14 adjacent auth/scoping tests green. Two `test_onboarding_m2` failures are pre-existing and unrelated — the dev box's Starlette 1.3.0 rejects the deprecated `TemplateResponse(name, dict)` signature the existing `/onboarding` route uses; prod pins fastapi 0.115 where it works, and the new `/home` route uses the forward-compatible `TemplateResponse(request, name, ctx)` signature so it is immune. Logged as a develop-gate enhancement candidate (add a Python/pytest class).

## Security follow-up (Tamir, pre-existing, before M6)

`app.py` sets `allow_origins=["*"]` with `allow_credentials=True`. This is pre-existing and currently NOT exploitable because the session cookie is `SameSite=Lax` + `HttpOnly` (a cross-origin credentialed fetch cannot attach it). M1 adds the first cookie-gated HTML page returning tenant business data, so tighten CORS to an explicit allowlist before M6 adds the supplier room, and never loosen the cookie to `SameSite=None` without fixing CORS first.

## Worktree note

Worked on the existing `spec/production-landed-cost-engine` branch in the dedicated beans-assistant checkout: it is clean, no concurrent session was live (sibling worktrees are stale `emc-*` from another project), and `.qie/context.yaml` names `interview-copilot` as active, so `bin/qie worktree auto` would have keyed off the wrong project. The dedicated spec branch is the isolation here.
