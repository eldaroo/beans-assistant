# Mockup iterations - Control Center unification

The user-facing surface was designed before implementation. The mockup lives next to the
spec at `./index.html` + `./styles.css` + `./fixture.js` and is the visual contract any
/develop run inherits. It renders the Home (7 tiles + attention strip) and the exemplar
new CRUD page (Productos), with all four states, three volumes, mobile + desktop, and
Timonel docked. Spanish copy, the product's language.

## Iter 01 - 2026-10-14 (built from the panel direction)

Built the mockup from Kaze's creative direction and Sally's UX notes. Kaze recommended the
coffee/cream brand (the business sells beans) over the indigo Control Center. The mockup
shipped in coffee tokens.

**Class:** visual identity.

## Iter 02 - 2026-10-15 (brand corrected on Dario's call)

**Dario:** "no, pero mantengamos el diseño moderno q creamos, te acordas q hicimos una spec?"

Dario overruled the panel's coffee recommendation and chose to keep the modern Control
Center design (indigo/Inter, the look created in spec 003). Re-skinned the mockup tokens to
the modern look; structure unchanged. Updated spec.md, plan.md, and ARCHITECTURE.md D-024 to
record the override.

**Class:** visual identity.
**Change:** replaced the coffee/cream `:root` token values in `styles.css` with the modern
Control Center palette (indigo accent `#4F46E5`, cool off-white surfaces, Inter/JetBrains
Mono), light and dark. Re-captured `screenshots/iter-02-*.png`.
**Screenshots:** `screenshots/iter-02-home-desktop.png`, `iter-02-productos-desktop.png`,
`iter-02-productos-mobile.png`, `iter-02-empty-mobile.png`, `iter-02-home-dark.png`.

## Completion checklist (Section E of genesis-spec)

- **E.1 states.** empty / loading / populated (1, 50, 5000 volumes) / error (500, validation, 403) all rendered and reachable from the mockbar.
  feel: the empty Productos state feels like an invitation to add the first product, not a failure; the error-500 keeps the rest of the Control Center reachable so the owner is never stranded.
- **E.2 viewports.** mobile 375-ish (default, bottom nav bar) and desktop 1280 (held rail).
  feel: the mobile populated table feels readable at a glance with the right columns dropped, not crowded; the desktop home feels like one calm surface with the money tile reading first.
- **E.3 wired interactions.** Agregar opens the modal; Editar populates it; Eliminar confirms; modal closes via X, Escape, Cancelar; mockbar toggles re-render client-side.
  feel: opening and closing the add-product modal feels immediate and reversible, never a commitment.
- **E.4 affordance cues.** filled Agregar button, per-row Editar/Eliminar with icon and label (always visible, not hover-only), modal X, focus rings matched to hover weight.
  feel: every action announces itself at rest; a keyboard user sees the same affordances a mouse user does.
- **E.5 accessibility.** 44px touch targets, visible focus outlines, Escape closes the modal and returns focus, dark mode meets the same contrast, prefers-reduced-motion disables the transitions.
  feel: the surface feels operable at night and from the keyboard without any action hiding behind a hover.

## Free-form note (Kaze + Sally, across the two vueltas)

Alive: the money-first home, the mono numbers settling in, the held nav that never bounces,
the inviting empty state. Dead on the first vuelta: the coffee re-theme, cut on Dario's call
in favor of the modern design he already owns. The one cut carried forward: no inline table
edits, so there is a single validation surface (the modal), not two.

## Approved - 2026-10-15

**Dario:** "luce muy bien, pasame el develop headless command"
**Final iter:** 2.
**Mockup files frozen at:** `./index.html`, `./styles.css`, `./fixture.js`.
**Carry-forward to /develop:** any visible affordance in the approved mockup is binding for the
implementation. The modern Control Center design is the single owner brand; the four coffee
read-only pages migrate onto it; the legacy page stays coffee, Admin-only.
