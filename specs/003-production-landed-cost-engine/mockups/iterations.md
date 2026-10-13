# Mockup iterations — production-landed-cost-engine

Design pair: Kaze (creative direction), Sally (information architecture and accessibility). The mockup is a single self-contained `index.html` (inline CSS and ES module), served locally and published as a private Artifact for remote walk-through. It is the visual contract any build run inherits.

## Surface caps (E.1 three-volume mandate)

This surface is not a scrolling list, so the 1 / 50 / 5000 volume mandate is met by documenting the real caps:

- The component column caps at **6 by design** (materiales, mano de obra, packaging, envío, aduana, indirectos are the fixed cost components). Shown at full 6 with a mix of filled and pending.
- The country comparison caps at **3 by design** (Colombia, Armenia-Colombia, Costa Rica). Shown at all 3.
- The one scaling list is the bracelet-type picker; it is a select, shown with 3 fixture types and reflows unchanged at a realistic inventory size once the CEO sends the real list (spec OQ5).

## Iter 01 — 2026-10-13

Synthesized from the Kaze and Sally notes in `../.deliberation/` (design-notes). First frame for the CEO to walk.

### E.1 Mandatory states

- empty — a new type with nothing filled: one line of purpose, one CTA "Cargar la receta", no orphaned shell. feel: the empty state feels like an invitation to start, not a broken form.
- loading — a six-row skeleton plus a headline skeleton, never a spinner, never a frozen blank. feel: the wait feels like the shape is already there and filling in, not like nothing is happening.
- populated — the six-component column at a realistic mix (four filled, two pending) summing down to a partial USD total; the complete state is reachable by saving a pending line. feel: the populated state feels readable at a glance, the eye lands on the components first and the total last.
- error — three sub-states: server failure (guardar failed, data kept), validation (missing FX rate, correctable), no-permission (margin is owner-only, supplier sent to their own room). feel: each error feels like the system taking responsibility and pointing at the next step, not scolding.

### E.2 Mandatory viewports

- mobile 375 canonical: single column, selectors stack, compare cards stack, CTA within thumb reach. feel: the phone view feels calm and one-thing-at-a-time.
- desktop 1280 enhancement: two-column (cost column plus a compare rail), compare cards sit side by side. feel: the desktop view feels like the same page breathing wider, not a different design.

### E.3 Wired interactions

Every AC verb has a real local-state handler in the mockup:
- click a pending row -> opens the fill form prefilled with that component name.
- click "Completar línea pendiente" -> opens the fill form.
- save the fill -> the row settles (chip becomes a mono value), the badge recounts, the total recomputes, and the pending note updates or clears.
- state tabs -> swap the visible state region.
- country segmented control and theme toggle -> wired.
feel: saving a line feels like a thing settling into place, and the total visibly stops being partial.

### E.4 Affordance clarity axis

- pending line: a neutral "Pendiente" chip with a dashed edge (not red, pending is not an error), and the whole 52px row is tappable with a hover and a focus ring. cue present.
- primary action: exactly one filled button "Completar línea pendiente"; filled values are plain mono text, not links, so known reads differently from unknown. cue present.
- country compare: a three-way segmented control, all countries always visible, the lowest complete marked with a "Más bajo" tag, not color alone. cue present.
- fill form: a labeled Cancelar control inside the form chrome, not only an outside click. cue present.
feel: the one pending line asks to be touched without shouting, and the "Más bajo" tag states the winner in words.

### E.5 Accessibility floor

- contrast: warm paper palette and the accent meet WCAG AA in light and dark. feel: legible without strain in daylight or at night.
- focus order: rows and controls are real buttons in reading order, visible focus rings. feel: keyboard moves where the eye moves.
- keyboard parity: rows open the form on Enter and Space; Cancelar returns focus. feel: nothing needs a mouse.
- touch: rows are 52px, controls at least 44px. feel: nothing is a near-miss on a phone.
- reduced motion: entrances and transitions collapse to fades without travel under prefers-reduced-motion. feel: calm for anyone who asked for calm.
- dark mode: a guarded dark palette meets the same AA contrast. feel: the evening workshop, not an inverted spreadsheet.

### E.6 Feel clauses

Present on every E.1 through E.5 row above.

### E.7 Free-form pass (Kaze and Sally)

What is alive: the total that refuses to lie. "Parcial · 4 de 6 componentes" over a warm USD figure is the whole product in one line, and watching it recompute to "Completo" when a pending line is saved is the exhale the CEO is paying for. The component column reading like a recipe, summing down to the answer, keeps the math honest and human. The supplier room is visibly a different, calmer place with no margins anywhere, which is the consent guarantee made visual rather than promised.

What is dead on arrival if we are not careful: the fill form is a stub, three inputs with no validation shown yet; the real one must show the computed USD the instant the rate is typed, so the supplier and the CEO see the normalization happen rather than trust it. One cut prescribed before the next vuelta: do not add a second accent color for the compare winner; the single "Más bajo" tag carries it, and a green number would start a palette the rest of the page does not speak.

## Iter 02 — 2026-10-13 (reframe to Beans Control Center)

**Dario:** "la plataforma tiene como objetivo final nuclear todas las cosas importantes del negocio. onda control center". And: the precise cost calculator is "mas para charlar con Claude en vivo"; the platform holds the numbers, the assistant runs the scenarios.

**Class:** scope-breaking. The mockup loop stopped, the spec returned to Phase 4 and was re-synthesized into the Beans Control Center with costing as one module, then Phase 4.5 re-entered. The reframe panel (Winston, Compass, Bob) resolved the shell architecture (D-020 to D-023); the status-home mockup below applies the same visual language Kaze and Sally set in iter 01, so the design pair was not re-dispatched for a surface that is a direct application of the established system. Deeper creative iteration on the home can re-dispatch the pair when needed.

**Change:** the default surface is now the status home (`#s-home`): an attention strip of three signals (café bajo, aduana pendiente, check-in de Víctor atrasado) over a six-tile scorecard (Caja con runway, Stock, Ventas, Margen parcial, Producción vs meta, Proveedores). The costing component card from iter 01 becomes the "Costos" module drill-down, reachable from the Margen tile and the aduana alert, and now carries the assistant-scenario ask line. The supplier room stays a separate surface.

### Scorecard cap note (E.1)

The home scorecard caps at Compass's 4 to 6 headline numbers by design (one headline per module, D-020). Shown at six. The attention strip caps by severity (D-021); shown at three across severities high and mid. The one scaling list is still the bracelet-type picker inside the Costos module (OQ6).

### States and feel (iter 02 home)

- home populated: attention strip plus six tiles. feel: the CEO answers "where am I, what needs me today" in the first second, then the numbers.
- home empty: one line of purpose plus one CTA, no orphaned grid. feel: the empty home feels like a start, not a dead dashboard.
- home loading: a headline skeleton plus four tile skeletons, no spinner. feel: the shape is already there and filling.
- home error: a per-module failure (Ventas tile did not load, the rest stands), a validation error, and a no-permission error (margin is owner-only). feel: a broken module is contained, the home does not go dark.
- costos drill-down: the iter-01 honest cost card, unchanged, plus the assistant-scenario ask line. feel: the number that refuses to lie, now reachable one tap from the alert that names its gap.
- attention strip: severity-ordered, capped, each item links to the one action that clears it. feel: the strip is a short list of today, not a second inbox.

### E.3 wired interactions (iter 02)

State tabs switch surfaces; every tile and every attention item navigates (`data-go`); the Margen tile and the aduana alert open the Costos module; a pending cost row and the "Completar línea pendiente" button settle the line, recount the badge, and recompute the total; the theme toggle works. Tiles without their own mockup surface return to the home for now, which is the honest state of a mockup whose later modules are M3 onward.

### E.7 free-form pass (iter 02)

What is alive: the home reads as a command center, not a report. The attention strip on top answers "what needs me" before the tiles answer "how am I doing", which is the order a founder actually thinks in. The Margen tile wearing "parcial · falta aduana" carries iter 01's honesty up to the home, so the whole platform tells the truth about what it does not know, not just the cost screen. One cut prescribed before any next vuelta: do not let the six tiles grow to nine; the three later-module tiles (Margen, Producción, Proveedores) must each earn the home by driving a weekly decision, per Compass, or they drop to a drill-down and the home stays at the numbers the CEO checks daily.

## Iter 03 — 2026-10-13 (complete rebrand, modern UX-friendly control center)

**Dario:** "esta bueno. Ahora necesitamos hacer un rebranding completo. tiene q ser un control center moderno y ux friendly". Chose a clean light-SaaS direction with a free hand on the identity (no existing brand colors or logo to honor).

**Class:** visual identity. Kaze was re-dispatched for a complete design system; the structure, IA, and cohorts are unchanged. The system is at `../.deliberation/mockup/kaze-rebrand-system.md`.

**Change:** the whole mockup was reskinned from the warm-paper workshop aesthetic to a modern light-SaaS control center. Applied tokens: background `#F6F7F9`, white surfaces, subtle `#E4E7EC` borders, a single indigo accent `#4F46E5` (hover `#4338CA`, soft `#EEF0FE`), Inter for UI and JetBrains Mono for every money figure, 12px card radius, the two-layer shadow recipe (flat tiles earn shadow on hover, the attention strip floats one layer up), a 4px spacing scale with 24px tile padding and 16px gaps, and a 240px left-rail nav on desktop that collapses to a top bar on mobile. The dark counterpart is recolored, not inverted (`#0C0E12` background, `#818CF8` accent). The attention strip now uses shape icons (filled triangle for danger, filled circle for warn, outline circle for info) so color is never the only cue. The honesty treatment is sharpened: the partial total now reads `USD 3.35 +` with a caption `Faltan 2 componentes: envío y aduana`, the Kaze "refuse false precision" move carried into the new system.

### States and feel (iter 03)

- home: left-rail nav plus attention strip plus a three-column scorecard. feel: it reads as a modern, trustworthy control center, calm and current, not a generic admin template.
- costos drill-down: the component column in the new system, the total wearing its `+` and the pending-count caption. feel: the honesty survives the restyle; the gap is still in the open.
- supplier, empty, loading, error: all reskinned to the system; the error states keep the shape-icon severity cues. feel: consistent, one system across every surface.
- dark mode: a recolored evening palette meeting the same AA contrast. feel: the same product at night, not an inverted sheet.

### E.5 accessibility (iter 03)

Every foreground/background pair in the Kaze palette targets WCAG AA; severity uses shape plus color, never color alone; touch targets stay at or above 44px; reduced motion collapses to opacity-only.

### E.7 free-form pass (iter 03)

What is alive: the single indigo accent plus generous white space makes the home feel like a current product, and the mono-aligned numeric grid gives the scorecard the authority of fact. The attention strip floating above the tiles on a soft shadow is the one move that says command center rather than list. What is dead if we are not careful: the three later-module tiles (Margen, Producción, Proveedores) still show numbers the backing modules do not yet produce; the build must not render a confident tile over a module that is not live, it shows that tile's own empty or pending state until its module lands. One cut prescribed: keep the accent to one color; a second accent for the compare winner or for a module family would dilute the calm the single indigo buys.

## Approved — 2026-10-13

**Dario:** "me encanta. tirame el develop headless command q drena todo".
**Final iter:** 03 (iter 01 costing card, iter 02 control-center home reframe, iter 03 complete rebrand to modern light SaaS).
**Mockup frozen at:** `./index.html`, published private Artifact `https://claude.ai/artifact/Hc1kvgPSGq1kRHahHuXLnh`.
**Carry-forward to /develop:** any visible affordance in the approved mockup is binding for the implementation. The design system at `../.deliberation/mockup/kaze-rebrand-system.md` is the token contract; the honesty treatment (a total that refuses false precision) and the two-separate-rooms rule (supplier vs owner) are binding. T-000 ports this mockup into the production status-home surface and ships first.
