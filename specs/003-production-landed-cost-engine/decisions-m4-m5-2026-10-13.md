# M4 + M5 build decisions — Beans Control Center multi-country, logistics, suppliers, scenario

Run: `beans-cc-m4m5-20261013-193858` (/develop --headless, continuation drain, cohorts M4 + M5 per genesis-build Section J).
Date: 2026-10-13. Defensible defaults taken under the /develop autonomy authorization. Each is reversible and disclosed. Builds on the merged M1 shell (#134), M2 costing (#135), M3 production (#136).

## Scope

- **M4** (surface S5): #122 T-014 indirect-cost allocation per unit per country per month (AC12), #123 T-015 three-country compute + margin (AC9), #124 T-016 Logistica module shipping/customs + the pending-customs signal (AC8 logistics side).
- **M5** (surface S6): #125 T-017 Proveedores directory + status, #126 T-018 overdue supplier check-in signal (AC13), #127 T-019 Timonel COST_SCENARIO read-only recompute (AC10).
- **Deferred (drain-around, Section J.2):** M6 (#128 T-020, #129 T-021, S7) and M7 (#130 T-022, #131 T-023, #132 T-024, S8) carry `external: named-human-signoff` (Andreas for the auth kernel + competitive-data scope; Dario with Re'i co-attestation for the external WhatsApp send). The integral-arc gate permits these as tracked external deferrals.

## Decisions

- **D-M4-1 — The indirect denominator is derived from production_records, not the stored `units_produced` column (AC12, realizing D-M3-9).** `CostingService.indirect_per_unit(country, month)` reads the pool (`indirect_costs.pool_cents` via `indirect_pool_latest`) and divides by units PRODUCED that month, summed from `production_records`. The legacy `indirect_costs.units_produced` column is left in place (schema compatibility) but no longer read. New write path `record_indirect_pool` stores the pool with `units_produced` NULL. Two M2 landed-cost tests that seeded the old column were updated to seed `production_records` instead (the data source changed per the spec plan, not a regression).

- **D-M4-2 — Month attribution by the week's Thursday.** `month_of_iso_week` maps `YYYY-Www` to `YYYY-MM` via `date.fromisocalendar(year, week, 4)` (the Thursday, the ISO-8601 rule that fixes a straddling week's month). `units_in_month` sums the newest row per (country, week), so a same-week append-only correction is not double-counted (the week_rollup / latest_per_country discipline). The SQL cannot do ISO-week date math portably, so the repository returns deduped weekly rows and the service maps and sums.

- **D-M4-3 — Margin uses `products.unit_price_cents` as the USD reference sale price, and is never shown off a partial cost or without a price (AC9).** Margin = sale price − landed cost, computed ONLY when the landed cost is COMPLETE and a price is set; otherwise pending with a named reason ("sin precio de venta" / "costo parcial · falta ..."). This is the only price field the schema carries and the costing domain is USD-cents throughout; if the business keeps the sale price in local currency this is the known follow-up (bounded by only ever showing a margin on a complete cost). The per-country comparison marks the lowest COMPLETE total as "cheapest to land"; a parcial total never wins.

- **D-M4-4 — Logistica is a dedicated lens over the SAME shipping/customs rows the landed cost reads, with its own module + drill-down.** No new tables (shipping_lanes/customs_duties exist from M2). New write paths `record_shipping_lane` / `record_customs_duty` (usd_amount_cents nullable = pending, never zero). The Logistica tile headlines the cheapest COMPLETE lane (shipping + customs) across the three countries; the pending-customs attention signal (MID) is computed from stored data, no message sent. Registered at order 60, route `/logistica/{phone}`, owner-gated, frozen design tokens.

- **D-M5-1 — `suppliers.last_checkin_at` column for the overdue signal; a null check-in is NOT overdue (AC13).** Added across the four schema sources (database_pg create, tenant_manager default, root_archive reference, and run_05 forward migration as an idempotent `ALTER TABLE ADD COLUMN IF NOT EXISTS` over `public.tenants`). Overdue = an active supplier whose last check-in is strictly older than the window; a supplier with no recorded check-in yet is never overdue (no false alarm on a freshly added supplier, the D-M3-2 blank-date discipline). The signal reads stored data only; the send path stays in M7.

- **D-M5-2 — The check-in window default is 14 days (OQ4), surfaced as a service setting.** `SupplierService(window_days=CHECKIN_WINDOW_DAYS=14)`; a sensible starting cadence the CEO tunes later (OQ4 is the CEO's to set).

- **D-M5-3 — Proveedores is the OWNER's lens; the two-rooms supplier self-service is M6.** The module shows the active directory with each supplier's check-in status and the overdue signal; no margins/prices/costs render on this surface (the D-017 two-rooms rule begins here). The supplier self-service login that lets a supplier see only their own data is the human-gated M6.

- **D-M5-4 — COST_SCENARIO is a deterministic read-only pre-check before the LLM graph (AC10).** `cost_scenario.handle_message` detects a clear hypothetical (keyword + the tenant's own bracelet types/countries), recomputes via `CostingService.landed_cost(..., overrides)` (the pure M2 recompute core, D-022), and returns a Spanish reply; a non-scenario message returns None so the normal LangGraph pipeline runs untouched. Wired into `ChatService.chat_with_tenant` inside the tenant scope, before `_invoke_graph`. It writes nothing (proven by a row-count assertion across all nine costing tables). The LLM router is not modified; the deterministic pre-check makes the no-write AC testable headlessly. v1 scenario semantics are a location move (baseline = the type's current country, scenario = the named country); overrides are carried for future phrasings.

## Verification note

The `bin/qie develop` gate is Node/TS only and returns CANNOT-VERIFY on this FastAPI/Python repo (SKIP tsc/lint; no SCRATCH_DB_URL for the db-migration class), so each of the five ledger milestones (m4-indirect, m4-margin, m4-logistica, m5-proveedores, m5-scenario) is stamped DEFERRED-NO-GATE with the pytest run as the authoritative verification (4th confirmation of this on the repo: M1/M2/M3/this).

- New this cohort: **55 tests** (34 M4: indirect allocation/month-math/margin/comparison/logistics/write-paths; 21 M5: supplier directory+overdue+write-paths, cost-scenario recompute+no-write+handler, run_05 migration).
- Full non-browser suite: **552 passed, 19 skipped, 2 failed**. The 2 failures are the pre-existing, unrelated `test_onboarding_m2` Starlette-signature failures at `app.py:186/190` (`onboarding_page`, untouched; confirmed failing on master HEAD 862bbe6). The new routes use the forward-compatible `TemplateResponse(request, name, ctx)` signature and are immune.

Mar'ah pre-flight (Section O) passed by AC-coupling for all five milestones, each with three literal spec citations, no override.

## Post-council amendments

A six-member council (Winston, Marcus, Edut, Tamir, Compass, Kaze) reviewed the change-set: five APPROVE-WITH-NITS and one BLOCK (Edut). All surviving BLOCKER/HIGH/MAJOR/MED findings were fixed inline and the suite re-run green (57 cohort tests + 554 full-suite).

- **D-M4-5 (fixes Edut BLOCKER) — the Costos tile never formats a missing margin as "USD 0".** `costos_module.compute_snapshot` now filters on margin availability (`not m.is_pending` = complete cost AND price set), not just landed completeness. A complete cost with no sale price shows the landed COST with "sin precio de venta" (tone flat); only a real margin headlines a margin.
- **D-M4-6 (fixes Edut HIGH / Marcus MED / Winston MED) — the scenario delta states a precise sube/baja only when both sides are complete.** `ScenarioResult` carries `baseline_status`; `format_reply` suppresses the direction and presents both totals as floors when either side is parcial, naming that the comparison is not yet precise. No false-precise delta.
- **D-M4-7 (addresses Edut MAJOR) — the USD sale-price assumption is disclosed at every margin surface** ("· precio USD" on the tile, "· precio en USD" on the drill-down). **Tracked follow-up:** give the product sale price the same `currency` + `fx_rate` -> USD normalization the cost inputs already carry (`input_purchases`), so price and cost are in the same unit before subtracting. This is a products-model change outside the M4/M5 costing cohort; until then the surface discloses the assumption so no margin is shown as a silent cross-currency figure.
- **D-M4-8 (fixes Compass MED) — Costos no longer re-signals shipping/customs pending.** Those are the Logistica module's domain (T-016); Costos' pending-component attention excludes Envío/Aduana, so a missing logistics line raises exactly one strip item (from Logistica), never a duplicate from both modules.
- **D-M5-5 (fixes Winston MED) — the COST_SCENARIO pre-check claims a turn only when a country is identified.** `handle_message` returns None (falls through to the normal pipeline) when no country is detected, so a general question that merely matched a trigger keyword is not hijacked by the costing path.
- Nits fixed: dead `indirect_latest` removed (Marcus LOW); redundant `product()` fetches folded in `country_comparison` (Winston LOW); money rendered in mono on the Logistica and Costos-comparison captions (Kaze LOW); dead CSS removed (Kaze NIT); a 03->05 ordering note added to `03_costing_tables.sql` (Winston NIT).
- Accepted as follow-ups (not blocking): the Costos home tile fans out a 3-country comparison (~bounded sequential reads, behind the home deadline + degrade-to-tile; Winston MED/perf) — a per-snapshot memoization/batch is the optimization if it ever trips the timeout.
