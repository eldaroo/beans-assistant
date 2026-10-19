> Tracked as eldaroo/beans-assistant#194

# Spec: Simplify the Command Center (AI-first, three tabs)

## Problem

Beans Command Center shows the owner a nine-entry navigation rail: Inicio plus eight operational modules (Resultado, Productos, Stock, Ventas, Costos, Producción, Logística, Proveedores). That rail is the engineering decomposition leaking onto her screen. The modules are factored around the database and the module registry, not around the jobs the owner actually does. For one non-technical person running a small real business across three countries, the cost is not clicks. It is the standing question "where do I go to do this" on every task, every time. We are installing Timonel, an AI that can already write sales, stock, products and expenses and read analytics from plain language. The AI changes the economics of the nine-door filing cabinet: if she can ask the question in words, the doors stop earning their cost. The job to be done is to run the whole business from one place, mostly by talking to Timonel, with the numbers visible and trustworthy enough to act on.

## Why now

Timonel's write and read tooling already exists over `/api/tenants/{phone}/chat` (spec 001, 005). The Control Center was just unified into one surface this month (spec 004 plus the single-business and unify work), so the shell is stable and the module registry is the single source of truth. The one missing move is to stop presenting the registry as the owner's menu and let the AI be the primary way to operate. Doing it now, before the owner builds nine-module habits, is cheaper than retraining later.

## Scope

### In scope

- Collapse the nine-entry rail into three job tabs: Hoy, Operación, Costos y producción. Tab membership is one `group` field on the module registry.
- Promote Timonel from the bottom-right corner widget to a persistent primary column (Hoy tab is where it is the main action surface). Single mount kept.
- A one-sentence plain-language daily-truth headline at the top of Hoy, computed from the existing status data.
- Persist and rehydrate the chat thread across tab switches (sessionStorage keyed by phone, server thread as fallback).
- Extend the chat-to-content contract (`beans:navigate` gains `{tab, module}`; `beans:refresh` stays per-surface).
- Group the existing `home_service` snapshot fan-out output by tab. No new query.
- The AI-write trust floor: confirm-before-write for money and stock mutations, a visible write-receipt on the active tab, an owner-readable change history ("qué cambió Timonel"), and undo within a defined window.
- Capability discovery on Hoy (example prompts) and an honest AI fallback (on an action it cannot do, it says so and links the exact section).
- Mobile layout: tab bar plus a collapsible Timonel sheet, no horizontal scroll.

### Out of scope

- No merging of the eight module pages into one combined page or factory. Each module keeps its route, its `_build_view`, and its single Alpine factory (ARCHITECTURE D-032).
- No change to routes, APIs, providers, auth, multi-tenant scoping, or the snapshot timeout bound (D-027).
- No removal of any module. Demoting the four deeper modules to chat-only is an explicit open question, not a v1 action.
- No tenant-configurable tabs.
- No change to the WhatsApp channel.
- No new LLM capability for Timonel beyond what the trust floor requires (confirm, flag inferred fields, re-ask on low confidence). New domain tools are a separate spec.

## Acceptance criteria

Each criterion is independently verifiable.

- **AC1.** The owner-facing rail renders exactly three tabs (Hoy, Operación, Costos y producción) on desktop and as a three-item nav on mobile, driven off a `group` field on the module registry. Adding a `group` to a new `Module` descriptor places it in that tab with no template edit. Verify: `backend/modules/protocol.py` has a `group` field; `registry.py` sets it on all eight modules; the rendered `cc_base.html` rail shows three tab labels; a unit test asserts `nav.owner_tabs()` returns three groups covering all eight modules.
- **AC2.** The Hoy tab renders the Timonel chat as a primary layout column (not a bottom-right floating widget) on desktop at >=1000px, and as a collapsible sheet on mobile at <=400px, while the chat factory `window.beansChat` mounts exactly once. Verify: `cc_base.html` mounts the slot once; the Hoy route renders the chat in the main region; pixel check at both viewports.
- **AC3.** The Hoy tab shows a one-sentence daily-truth headline above the chat, generated from the current status data (counts of today's sales, unpaid sales, and the top attention item), in plain Spanish, present even in the empty state ("Todavía no hay movimientos hoy"). Verify: the headline string is produced by a pure function from `build_home` data; a unit test asserts the sentence for a fixture with two paid sales and one low-stock item.
- **AC4.** The chat thread survives a tab switch and a full-page navigation: after sending a message and navigating to Operación and back to Hoy, the prior messages are still visible. Verify: `chat_widget.js` writes the thread to `sessionStorage` keyed by phone and rehydrates on load; a browser walk sends a message, navigates, returns, and asserts the message is present with zero console errors.
- **AC5.** A `beans:navigate {tab, module}` event switches to the named tab and drills into the named module; a `beans:navigate` to a module in the current tab does not full-reload. Verify: the shell tab-router maps `{tab, module}` to the content; a browser walk dispatches the event and asserts the active tab and the opened module.
- **AC6.** Grouped tiles: the Hoy tab shows the full status home tiles plus the attention strip; Operación shows only its group's tiles; Costos y producción shows only its group's tiles. The home snapshot fan-out runs once per home load, not per tab switch. Verify: `home_service.build_home` output is grouped by `group`; a test asserts the tile subset per tab and that no extra query fires on tab switch.
- **AC7.** Every Timonel write to money or stock shows a confirmation preview in plain language before it commits ("Registro venta: 2 termos, 90.000 COP, pendiente") and commits only on an explicit yes. Verify: a chat-driven sale returns a preview payload and waits; a test asserts no DB row until the confirm step. Routes to `requires_human_review` for the threshold policy (AC9).
- **AC8.** After a committed Timonel write, the written row appears on the active tab (a visible receipt card or the refreshed list row), and a persistent owner-readable change entry is recorded ("qué cambió Timonel": the action, the before and after value where applicable, the timestamp, and the phrasing that triggered it). Verify: a chat-driven expense produces a receipt on screen and one change-history row readable in plain Spanish.
- **AC9.** A threshold policy names which Timonel writes auto-confirm and which require explicit confirmation or human review: cancel or delete of a sale, stock set to zero, an expense above a configured amount, a product price change, and any write where Timonel inferred a field the owner did not state. This AC is `requires_human_review` and routes to Andreas plus Edut for sign-off before its children materialize. Verify: the policy table exists in the spec or a config; the sign-off is recorded.
- **AC10.** Undo: a Timonel-committed write is reversible from the surface within a defined window without the owner composing a counter-entry. Verify: a chat-driven write shows an undo affordance; invoking it reverses the write and records the reversal in the change history (append-only; the original write entry is kept).
- **AC11.** On an action Timonel cannot perform, it says so in plain language and links the exact section or page that can do it; it does not fail silently or claim success. Verify: a prompt for an unsupported action returns a message plus a working link to the relevant tab/module.
- **AC12.** No regression: the eight module pages render unchanged under the new tabbed rail, all eight CRUD endpoints behave as before, and the home renders every number as it does today. Verify: the existing suite stays green; a pixel self-regression gate runs over the reshaped shell with the current home as golden.

## Whole-problem surface

```yaml
surfaces:
  - id: S1
    surface: "Three-tab shell driven by a registry group field; grouped tiles; no route change"
  - id: S2
    surface: "Timonel promoted to a persistent primary column, single mount, mobile sheet"
  - id: S3
    surface: "Chat thread persistence and rehydration across tab switches (sessionStorage + server thread)"
  - id: S4
    surface: "Chat-to-content contract extended with {tab, module}; shell tab-router"
  - id: S5
    surface: "AI-write trust floor: confirm-before-write, visible receipt, owner-readable change history, undo"
    external: "named-human-signoff (AC9 threshold policy; Andreas + Edut; tracked on the parent issue)"
  - id: S6
    surface: "Hoy daily-truth headline and capability discovery; honest AI fallback on unsupported actions"
  - id: S7
    surface: "Mobile layout (tab bar + chat sheet) and usage instrumentation for the 30-day re-group decision"
```

## Mockup

The user-facing surface was designed before implementation via a four-iteration mockup deliberation (Kaze's panel design direction plus Quinn's UX synthesis). The frozen mockup lives at `./mockups/index.html` and is the visual contract any /develop run inherits. T-000 ports it into the production Hoy surface.

- Screens covered: three tabs (Hoy, Operación, Costos y producción); the Timonel drawer on desktop and bottom sheet on mobile; per-module view and edit drill-ins reached from tiles; audio recording.
- State machine: empty, loading, populated, error on the surface; chat idle to recording to voice note to transcription to confirm to receipt to undo.
- Iterations: 4 (see `./mockups/iterations.md`).
- Approved on: 2026-10-19.
- Design panelists: Kaze, Quinn.
- Binding affordances: Timonel is collapsed by default with a microphone launcher (voice-first); opening it offers both typing and recording; a money or stock write originating from voice passes the same confirm, receipt and undo trust floor as a typed one; every module is reachable and editable via tile drill-ins, nothing is chat-only.

## Open questions

- **A-Q13 (tab count).** Three tabs, or two. The 2-tab camp (Simplifier, Mary) folds Costos y producción into Operación or into Timonel, and argues the four deeper modules are read rarely and their signals already surface in Atención, so they should not be top-level and their pages could be removed. The 3-tab camp (Winston, Kaze, Amelia) keeps all pages as drill-downs because deleting modules loses function the owner still needs occasionally and because grouping is one field edit, reversible. Right person: Dario, at the mockup gate. Default the workflow proceeds with: three tabs, re-group by observed use after 30 days (one field edit), modules kept.
- **A-Q14 (Timonel placement).** Left column or right column on desktop; persist or collapse on mobile. Right person: Dario at the mockup gate. Default: right column on desktop, collapsible sheet on mobile.
- **A-Q15 (tab content).** On Operación and Costos y producción, tiles-with-drill-in, or a primary module rendered inline with a sibling rail. Right person: panel re-deliberation if the owner bounces. Default: tiles with drill-in (reuses the snapshots, cheapest).
- **A-Q16 (write confirmation).** Does a money write through Timonel require a visible confirmation card on the active tab before it is considered done. Right person: Edut plus Mar'ah on the trust question. Default: yes, surface the written row inline via `beans:refresh`.
- **A-Q17 (daily-truth source).** Is the Hoy headline computed deterministically from `build_home` data (v1 default) or phrased by a Timonel read call. Right person: Kaze plus Dario on feel. Default: deterministic from status data for v1; Timonel phrasing is a follow-on.

## Panelists who contributed

- Mary (Business Analyst) — named the real job-to-be-done and the measurable 90-day signals; flagged that the nav mirrors the hidden schema.
- Winston (Architect, author of the architecture delta) — the three-tab grouping as one registry field, keep the pages as drill-downs, no domain rewrite (D-029 to D-033).
- Amelia (Developer) — the chat-state-dies-on-navigation finding; the concrete nav-only implementation path on `cc_base.html` and `registry.py`.
- Kaze (Creative direction) — the three-tab felt shape, Timonel as the main column, and the daily-truth sentence as the actual product.
- Edut (Moral conscience) — the Sacred-check floor: confirm, receipt, undo, owner-readable change history; which writes route to human review.
- Simplifier — the 2-tab minority position and the finding that four modules exist twice (as a tile the owner reads daily and a page she rarely opens).
