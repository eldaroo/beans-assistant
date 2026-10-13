> Tracked as eldaroo/beans-assistant#133

---
name: beans-control-center
spec_ordinal: 003
slug_note: directory kept as 003-production-landed-cost-engine; the spec was reframed mid-run from a landed-cost engine into the Beans Control Center, with costing as one module.
target_repo: eldaroo/beans-assistant
run_id: production-landed-cost-engine-20261013-093842
architecture: update (D-013 through D-023)
---

# Spec: Beans Control Center

## Problem

Beans&Co makes coffee bracelets ("pulseras de café") and produces and ships across three countries (Colombia, Armenia-Colombia, Costa Rica) with outside suppliers. The CEO runs the whole business from scattered WhatsApp threads and his own memory. There is no single place that shows whether the business is healthy right now: production this week, cash, stock, margin, and what needs attention today all live in different heads and chats. The existing Beans platform holds sales, stock, expenses, and an assistant, but as separate pages, not as one command center. This spec builds the Beans Control Center: one platform that nucleates every important part of the business into a status home with an attention strip and uniform modules the CEO drills into. Knowing the true landed cost of a bracelet is one of those modules, not the whole thing.

## Why now

The CEO is actively running production, suppliers, and sales across three countries and has no at-a-glance view to run them from. The business already lives on this repo (Google-OAuth web app, schema-per-tenant Postgres, a Timonel assistant, a WhatsApp connector), so the control center builds on a spine that exists. The CEO has directed that this become the primary platform, with the prior sales and stock assistant folded in as first-class modules rather than left as a separate app.

## Scope

### In scope

- A command-center shell: a module registry and a two-provider protocol (a headline number and a set of attention items per module), so every domain plugs into the status home uniformly.
- A status home at the default route showing one tile per module plus an attention strip of what needs the CEO today, with drill-down into each module.
- The existing sales, stock, and expenses surfaces promoted to first-class registered modules, nothing deleted.
- A costing module: the per-tenant costing data model, multi-currency entry normalized to USD, and a landed cost per bracelet type per country that always carries a completeness state. The numbers live in the platform and are always shown.
- A read-only scenario path: the Timonel assistant can read a stored landed-cost snapshot and recompute a hypothetical ("what if I move display-stand production to Colombia") without writing. The heavy scenario UI is out; the conversation carries it.
- A production module (units per week, arrival cadence, durability), a suppliers module (directory plus status), and a logistics module (shipping and customs lines).
- Indirect-cost allocation (display stands and overhead) prorated per unit produced per country per month, and a per-country margin comparison.
- A supplier-as-user membership model so suppliers can log in and enter only their own data, never margins, prices, or another supplier's costs.
- Automated WhatsApp check-ins to suppliers reusing the existing Baileys connector and Timonel, with consent, truthful sender identity, a cadence cap, an opt-out, and a human fallback for replies that do not parse.

### Out of scope

- Live FX-rate fetching. The M2 rate is hand-entered per purchase; an automated rate source is a later capability.
- A heavy costing scenario UI. Scenario exploration is a read-only recompute the assistant runs; the platform shows the stored facts.
- A central rules engine for attention. Each module owns its own attention rules.
- A tenant-configurable module registry. The registry is a static list in M1.
- Any deletion or rewrite of the existing sales, stock, expenses surfaces or the assistant. The change is additive.
- Supplier visibility into margins, sale prices, or another supplier's costs, under every code path.
- A general ledger or invoicing system.

## Acceptance criteria

Each criterion is independently verifiable and names its surface and trigger.

- **AC1.** Adding a module descriptor to `backend/modules/registry.py` with a `headline()` and an `attention()` provider makes its tile appear on the status home and its items appear in the attention strip, with no edit to the home route or template; an integration test registers a fake module and asserts the tile and the attention item render.
- **AC2.** The default landing route renders status tiles for stock, cash, and sales sourced from the existing repositories, plus a low-coffee-stock attention item when stock is below its threshold; a test with seeded data shows the three tiles and the item.
- **AC3.** A module whose `headline()` raises renders a degraded tile and does not break the home; a test with a throwing provider asserts the rest of the home still renders.
- **AC4.** `attention_service` aggregates items across the registry, sorts by severity, and caps the strip at its limit; a test with more items than the cap asserts the cap and the severity order.
- **AC5.** Sales, stock, and expenses register as modules and remain reachable at their existing routes; the diff shows only additions and the new default route, with no route or template removed.
- **AC6.** Applying the costing migration (`create_tenant_schema` plus a forward loop over `public.tenants`) creates all ten costing tables on a fresh and on an existing seeded tenant schema; a test asserts each table per schema and that one bad schema does not abort the loop.
- **AC7.** Entering an input purchase in COP stores `original_currency`, `original_amount_cents`, `fx_rate`, and a derived `usd_amount_cents` in `input_purchases`; a correction creates a second row and never mutates the first.
- **AC8.** `costing_service.landed_cost(type, country)` returns a USD-cents total equal to materials (via the BOM) plus labor plus packaging plus shipping plus customs plus prorated indirect in a unit test; a null shipping or customs line is flagged and excluded, never summed as zero, and the snapshot renders `status=parcial` with the pending components named.
- **AC9.** The costing module exposes a margin-per-country headline and a per-country comparison for one bracelet type (Colombia, Armenia-Colombia, Costa Rica), each with its completeness state, and marks the lowest complete total.
- **AC10.** A COST_SCENARIO message to Timonel ("mover la producción de exhibidores a Colombia") returns a recomputed landed cost produced by `costing_service.recompute(snapshot, overrides)` reading the stored snapshot; a test asserts no new snapshot row is written.
- **AC11.** The production module records units produced per week against a target; direct labor entered as a batch payment computes per-unit labor by dividing by units completed, not planned, and a unit test shows a short batch raises the per-unit labor.
- **AC12.** Indirect cost allocates per unit as the indirect pool for a country in a calendar month divided by units produced there that month; a month with zero recorded production renders indirect PENDING, not a divide-by-zero.
- **AC13.** An overdue supplier check-in (no recorded reply within the configured window) surfaces as an attention item computed from stored data, with no message sent.
- **AC14.** A supplier user (non-owner) authenticates via Google OAuth and resolves to the tenant through `public.tenant_members`; a scope test proves that session cannot read any other supplier's costs, the margin, or any sale price. (requires_human_review: Andreas)
- **AC15.** No supplier login is active and no automated message is sent without a corresponding stored consent row, and the login consent and the messaging consent are separate records. (requires_human_review: Dario)
- **AC16.** A scheduled WhatsApp check-in sent through the existing Baileys connector names Beans&Co and states it is an automated message in its first line, respects a schema-enforced frequency cap and an immediate opt-out, and introduces no second channel. (requires_human_review: Dario, with Re'i co-attestation)
- **AC17.** A supplier WhatsApp reply that parses updates production through the Timonel PRODUCTION_UPDATE intent; a reply that does not parse is stored verbatim and routed to the CEO, never silently dropped and never force-written. (requires_human_review: Dario)

## Whole-problem surface

```yaml
surfaces:
  - id: S1
    surface: Command-center shell (module registry, two-provider protocol, fail-open tile, attention service)
  - id: S2
    surface: Status home over the existing sales, stock, and expenses data with the attention strip
  - id: S3
    surface: Costing module data model, multi-currency to USD, and the landed cost with completeness state
  - id: S4
    surface: Production module and cost-domain breadth (all input categories, labor completed-basis, packaging)
  - id: S5
    surface: Multi-country compute, indirect allocation, margin, and the logistics module
  - id: S6
    surface: Suppliers directory and the assistant read-only scenario recompute path
  - id: S7
    surface: Supplier membership login at the auth kernel plus within-tenant row scope
    external: named-human-signoff   # Andreas; auth kernel and competitive-data scope, AC14
  - id: S8
    surface: Consent ledger, automated WhatsApp check-ins, and the non-parsing reply fallback
    external: named-human-signoff   # Dario, Re'i co-attestation; external send to real third parties, AC15/AC16/AC17
```

## Mockup

The user-facing surface was designed before implementation across three mockup iterations with Kaze and Sally (iter 01 the costing card, iter 02 the control-center home reframe, iter 03 the complete rebrand to a modern light-SaaS system). The frozen mockup lives at `./mockups/index.html` and is the visual contract any build run inherits. The design-system tokens are in `./mockups/.. ` (the deliberation archive, `kaze-rebrand-system.md`).

- **Screens covered:** status home (attention strip plus a six-tile scorecard), the Costos module drill-down (component column summing to a landed cost with a completeness badge), the separate supplier surface, and the empty, loading, and error states.
- **Design system:** background `#F6F7F9`, white surfaces, one indigo accent `#4F46E5`, Inter for UI and JetBrains Mono for money, 12px radii, a two-layer shadow recipe, a 240px left-rail nav collapsing to a top bar on mobile, a recolored dark mode, and shape-based severity cues so color is never the only signal.
- **Honesty treatment (binding):** a partial total renders as `USD 3.35 +` with a caption naming the pending components, never a false-precise number.
- **Two-rooms rule (binding):** the supplier surface and the owner surface are separate routes; a margin never renders on any supplier view under any code path.
- **Iterations:** 3 (see `./mockups/iterations.md`).
- **Approved on:** 2026-10-13.
- **Design panelists:** Kaze, Sally (with Compass on the scorecard discipline).

## Open questions

- **OQ1 (indirect-allocation window).** Calendar month (Winston) versus a rolling trailing window (Marcus); both agree the denominator is units produced. Right person: Dario with the CEO. Default: calendar month, indirect PENDING until the month has recorded production. (A-Q5)
- **OQ2 (scheduler home).** The check-in scheduler as a Nomad periodic job or an in-process Baileys timer. Right person: Winston at build. Default: a Nomad periodic job. (A-Q6)
- **OQ3 (the home scorecard).** Compass recommends 4 to 6 headline numbers (units this week versus target, cash and runway, coffee-stock weeks, landed cost once populated, gross margin, open-attention count). The CEO confirms which earn the home first. Default: ship M1 with cash, stock, and sales tiles from existing data; add production and margin tiles as their modules land.
- **OQ4 (attention thresholds).** The concrete triggers (low stock below N weeks, overdue check-in after X days, cash runway below N weeks). Right person: the CEO, since Compass notes the signals should codify the rhythm he already runs. Default: sensible starting thresholds, surfaced as settings.
- **OQ5 (the invisible team).** María "works with a team" who do the labor, sit behind her login, and never appear on a screen. Right person: Dario and the CEO. Default: María's login is hers alone; her team is not attributed or exposed without its own consented step.
- **OQ6 (bracelet-type inventory).** The CEO will send the real inventory; the costing model does not block on it. It seeds fixtures and real costing once received.

## Panelists who contributed

First panel (costing frame): **Winston** (architecture), **Amelia** (dev, the auth-kernel and migration reality), **Marcus** (the landed-cost model and completed-basis labor), **Bob** (sequencing), **Kaze** (the honest cost card), **Edut** (the stakeholder map including María's invisible team), **Mar'ah** (the Legion Action Gate on the WhatsApp send).

Reframe panel (control-center frame): **Winston** (the shell: module registry, provider protocol, attention engine, the scenario read-path, D-020 through D-023), **Compass** (the scorecard discipline, the attention-signal set, and codifying the CEO's existing rhythm rather than imposing one), **Bob** (the re-sequenced arc putting the shell over existing data first and costing second), and the design pair **Kaze** and **Sally** on the status-home mockup.
