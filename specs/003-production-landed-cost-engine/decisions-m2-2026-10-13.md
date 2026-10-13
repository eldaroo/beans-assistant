# M2 build decisions — Beans Control Center costing module

Run: `beans-control-center-20261013-113520` (/develop --headless, continuation drain, cohort = M2 per genesis-build Section J).
Date: 2026-10-13. Defensible defaults taken under the /develop autonomy authorization. Each is reversible and disclosed. Builds on the M1 shell (decisions-m1-2026-10-13.md), appending the Costos module to the registry it established.

## Scope

Cohort = M2 only (surface S3: costing data model, multi-currency to USD, landed cost with completeness). Children #115-118 / AC6, AC7, AC8 plus the Costos module registration and drill-down (T-010). The spec has 25 children across 7 milestones; this run drained M2 end to end on top of the already-committed M1. M3 (production, AC11), M4 (multi-country compare + margin AC9, indirect allocation AC12 live), and M5 (suppliers + the Timonel COST_SCENARIO read-path AC10) append in later runs. M6/M7 stay behind their named-human gates.

## Decisions

- **D-M2-1 — The tile is labelled "Costos" (landed cost), not "Margen".** The frozen mockup's home tile reads "Margen 38%", but a margin needs a sale price compared per country, which is the M4 three-country compute (AC9). Shipping a tile labelled "Margen" over a landed-cost number would be the same metric overclaim the M1 council corrected for "Caja" -> "Resultado" (D-M1-2). M2 ships the tile as "Costos" showing the lead bracelet type's landed cost with its completeness state. The "Margen" headline lands in M4 when the per-country margin compute exists.

- **D-M2-2 — One country per landed cost in M2; the lead type and its first country drive the tile and the default drill-down.** AC9's per-country comparison (Colombia, Armenia-Colombia, Costa Rica) is M4. M2's `landed_cost(product_id, country)` computes one type in one country; the Costos tile and the `/costos/{phone}` drill-down pick the lead bracelet type (first active product carrying a BOM line) and its first country. `?product=&country=` overrides. Multi-country compare + the "mark the lowest complete total" (AC9) append in M4 with no change to this core.

- **D-M2-3 — The six landed-cost components are each filled or pending; a pending component is excluded from the total, never summed as zero.** Per D-016 and the binding mockup honesty treatment. Components: materiales (via the BOM x each input's latest USD unit cost), mano de obra (batch payment / units completed, AC11 completed basis), empaque, envío, aduana, indirectos. The pure `recompute(components, overrides)` core sums only filled components, names the pending ones, and sets `status` to `completo` only when all six are filled, else `parcial`. A partial total renders "USD X +" with the pending components named (never a false-precise finished number).

- **D-M2-4 — Materials is pending (named) if any BOM input is unpriced.** When a `bom_lines` input has no `input_purchases` row, its unit cost is unknown; rather than drop the line (understating materials) the whole materials component is pending and names the unpriced inputs. A complete materials number requires every recipe input priced. This is the materials-level application of the completeness honesty rule.

- **D-M2-5 — Indirect reads the latest recorded month; zero or no recorded production renders indirect PENDING (AC12, no divide-by-zero).** Indirect per unit is the country's monthly pool over units produced that month (D-015, OQ1 default = calendar month). M2 wires the table and the pending behavior; the full calendar-month allocation across production counts is M4. A month with `units_produced` null or 0 is pending, never a division error.

- **D-M2-6 — `input_purchases` is append-only; a correction is a new row (AC7, D-014).** `record_input_purchase` always INSERTs the stored triplet (original_currency, original_amount_cents, fx_rate) plus the derived `usd_amount_cents`. `fx_rate` is units of the original currency per 1 USD, so `usd_cents = round(original_amount_cents / fx_rate)`. No existing row is ever mutated, so a disputed cost or a wrong rate stays visible and re-checkable.

- **D-M2-7 — The status home template gains absolute-route support; Costos is the first dedicated module page.** M1 routed every module to a dashboard tab suffix (`?tab=...`, D-M1-5), which anticipated "dedicated module pages replace these routes as each module milestone ships." M2 adds the first dedicated page, `/costos/{phone}`, so the home template gained a small additive `href_for` macro: a route starting with `/` is absolute (with `{phone}` substituted), otherwise it is the base-plus-suffix M1 behavior. The three M1 tab routes are unchanged and the M1 regression suite stays green. Reversible: remove the macro and the Costos route reverts to a tab.

- **D-M2-8 — The ten costing tables land in all three schema sources.** New Postgres tenants get them from `create_tenant_schema`; new SQLite tenants from `tenant_manager._get_default_schema`; the SQLite test schema (`root_archive/init_complete_database.sql`) carries them so the suite can seed them. Existing Postgres tenants get them from the forward loop `postgres/migrations/run_03_costing_tables.py` over `public.tenants`, idempotent (CREATE TABLE IF NOT EXISTS) with per-schema try/rollback/continue so one bad schema does not abort the loop (AC6).

## Verification note

The `bin/qie develop` gate is Node/TS only and cannot classify a Python/FastAPI repo (SKIPs tsc/lint, DEFERS the db-migration class pending a SCRATCH_DB_URL convention), so the milestone stamps DEFERRED-NO-GATE and the authoritative verification is the repo pytest suite:
- M2 costing suite: **14 passed** (7 costing_service AC7/AC8/AC12 + pure recompute/scenario-override core, 4 costing_migration AC6 ten-tables/idempotent/loop-isolation, 3 costos_module integration AC1 tile+attention+route).
- M1 + adjacent regression re-run: **33 passed** (control-center shell/template/home/route, auth_redirect, api_scoping). No regression from the registry append, the template macro, the app.py router include, or the schema edits.
- Full non-browser suite: **481 passed, 19 skipped, 2 failed**. The 2 failures are the SAME pre-existing, unrelated `test_onboarding_m2` failures M1 recorded (the deprecated `TemplateResponse(name, dict)` at `app.py:184` on the dev box's newer Starlette). The new `/costos` route uses the forward-compatible `TemplateResponse(request, name, ctx)` signature and is immune.

## Security follow-up (still open from M1, before M6)

`app.py` sets `allow_origins=["*"]` with `allow_credentials=True`. Pre-existing; M2 adds a second cookie-gated HTML page returning tenant business data (the Costos drill-down), so the M1 note stands: tighten CORS to an explicit allowlist before M6 adds the supplier room, and never loosen the session cookie to `SameSite=None` without fixing CORS first. The Costos drill-down is owner-gated by `require_tenant_match`; the supplier two-rooms split (a supplier never sees a cost or margin, D-017) is M6.

## Deploy note

Not deployed in-run. The beans deploy is a manual path (merge to master, build and push the image, patch the Nomad job, run the forward migration on prod Postgres), and the prod cutover of a live business is Dario's standing confirm gate. M2 merges to main; the prod deploy and the `run_03` migration run on Dario's confirm. See the run closing for the exact commands.
