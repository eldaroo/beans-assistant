# Mockup iterations — Simplify the Command Center

Design direction: Kaze's Phase 3 panel review (three tabs, Timonel as the main column, the daily-truth sentence as the product) plus Quinn's UX synthesis from the panel. Sally was not separately dispatched; her information-architecture concerns (order, hierarchy, affordance, focus) are folded into this build and are open to a delta dispatch if Dario's feedback is information-arch class.

## Iter 01 — 2026-10-17

Built the first mockup: three tabs (Hoy, Operación, Costos y producción), Timonel as a persistent primary column on Hoy, the one-sentence daily-truth headline, status tiles with drill-in, the attention strip, and the AI-write trust choreography (send, confirm preview, commit, visible receipt, undo). Served at http://127.0.0.1:4180/.

### Completion-floor checklist (genesis-spec Section E)

- **E.1 states** — populated (default), empty, loading (skeletons), error (banner with retry). State switcher top-right.
  - feel: the empty state feels like an invitation ("pedile algo a Timonel para empezar"), not a broken shell; the error state keeps Timonel available so the owner is never fully stuck.
- **E.1 populated volumes** — this surface is a status-tiles + short-list surface by design, not a 5000-row table. Tiles are a fixed small set (4 per tab); the one list drill-in (Ventas) ships at a realistic small volume. Documented cap: the Command Center home caps at one tile per registered module (max ~8) and the deep tables live in the existing module pages, which are out of scope for this reshape.
  - feel: the populated Hoy reads in five seconds: one sentence, three attention lines, four numbers, one place to talk.
- **E.2 viewports** — mobile 390px (stacked, Timonel below the tiles) and desktop 1366px (two columns, Timonel right). Captured.
  - feel: mobile feels like one calm scroll, not a cramped desktop; desktop feels like talk-on-the-right, look-on-the-left.
- **E.3 wired interactions** — click tab (switch), click state (re-render), click tile (drill-in panel), click attention "Ver" (switch tab + drill), send message / click chip (reply), confirm "Sí, registrar" (commit + receipt + tile flash), "Cancelar" (abort), "Deshacer" (reverse), close "×" (dismiss panel), theme toggle.
  - feel: the write lands with weight (the tile flashes, the receipt appears and stays), so the owner sees the AI's action, not just hears it.
- **E.4 affordance cues** — chevron on tiles (drill), "Ver ›" on attention, "×" on the drill panel, chips as tappable suggestions, focus-visible outline on all controls.
  - feel: nothing is a mystery click; every surface that opens shows a cue at rest.
- **E.5 accessibility** — focus-visible rings, role=tablist/tab/tabpanel + aria-selected, aria-live log on the thread, 44px minimum controls, prefers-reduced-motion disables the flash and shimmer, dark mode via prefers-color-scheme and the tema toggle with WCAG-AA indigo/neutral tokens.
  - feel: the night operator gets a calm dark surface that is as readable as the day one.

### E.7 free-form note (Kaze + Quinn)

Alive: the daily-truth sentence carries the screen, and the confirm-then-receipt choreography makes the AI feel accountable, not magical. The three-tab rail finally reads like jobs, not modules. Dead: the deep tab (Costos y producción) is still just four tiles; it needs a reason to exist beyond "the leftovers," which is exactly the 2-vs-3-tab question for Dario. One cut prescribed before any next vuelta: if Dario leans two tabs, fold Costos y producción into a single "Ver más" drill from Operación and let Timonel be the door to the deep four, so the top level is Hoy and Negocio only.

### Open for Dario at this gate (iter 01)

- A-Q13: three tabs (this mockup) or two. The deep tab is the swing.
- A-Q14: Timonel on the right (this mockup) or left; mobile below (this mockup) or a launcher sheet.

## Iter 02 — 2026-10-19

**Dario:** "Tiene q ser tambien full responsive para el celu, en ese caso el boton para hablar con timonel tiene que quedar en la pantalla y verse. Por otro lado, no hay lugar para ver/editar los proveedores, y algunas otras cosas q valen la pena q esten."

**Class:** information arch (two changes). Changes made:

- **Mobile Timonel launcher.** Timonel moved from a column stacked below the tiles to a persistent fixed launcher ("Hablá con Timonel") pinned bottom-right on every tab at <=900px; tapping it opens Timonel as a full-height bottom sheet with a close and a backdrop. On desktop Timonel is now a shared sticky right column present on all three tabs, not only Hoy. This also resolves A-Q14: right column on desktop, fixed launcher plus sheet on mobile.
- **View and edit for the deep modules.** Every tile now drills into a real view/edit surface. Proveedores opens a table (Proveedor, Contacto, Último check-in, Estado) with an Editar action per row and an Agregar proveedor button. The same pattern covers Costos, Producción, Logística, Productos, Stock, Ventas, Resultado. Nothing is chat-only; everything the owner needs is two taps away and editable. This resolves A-Q13 toward three tabs with the deep modules kept and reachable, not demoted.

**Re-dispatched:** none (cosmetic and IA edits by Quinn).
**Screenshots:** `screenshots/iter-02-mobile.png`, `screenshots/iter-02-mobile-timonel.png`, `screenshots/iter-02-desktop-proveedores.png`.

feel: on the phone Timonel is always one thumb away, so the AI stays the way you operate even on the small screen. The deep tab stopped feeling like leftovers now that each tile opens a real editable table; the owner can see and fix suppliers, costing, production and shipping without asking anyone.

### Open for Dario at this gate (iter 02)

- A-Q13 now leaning three tabs (deep modules kept and editable, per this iter). Confirm or ask for two.
- A-Q15: tiles-with-drill-in (this mockup) stays the default; confirm it reads right.

## Iter 03 — 2026-10-19

**Dario:** "timonel should be colapsed by default. and desktop version isn't working well."

**Class:** information arch / visual identity. Changes made:

- **Timonel collapsed by default, everywhere.** It is no longer a persistent open column. Default state is collapsed, with an always-visible launcher ("Hablá con Timonel") pinned bottom-right. On desktop Timonel opens as a right-side drawer with a dimmed backdrop and a close; on mobile it opens as a bottom sheet. This resolves A-Q14 to: collapsed by default, launcher-opened drawer (desktop) / sheet (mobile).
- **Desktop fixed.** The previous persistent 420px right column left a tall empty panel beside short tabs and cramped the content. With Timonel collapsed, the content region is full width: the daily-truth headline spans the row, the attention strip is full width, and the tiles lay out four across. The drawer only takes space while open.

**Re-dispatched:** none (layout and state edits by Quinn).
**Screenshots:** `screenshots/iter-03-desktop-collapsed.png`, `screenshots/iter-03-desktop-open.png`.

feel: at rest the screen is just the business, calm and full width, and Timonel is one tap away without ever being in the way; opening it feels like turning to talk to someone, then turning back to the numbers.

## Iter 04 — 2026-10-19

**Dario:** "el boton en vez de habla con timonel podria ser un simbolo para grabar audio directamente, o de chat. Cuando lo abris deberia dar la opcion para grabar audio tmb."

**Class:** visual identity / interaction. Changes made:

- **Launcher is now a microphone FAB.** The text pill became a round accent FAB with a mic icon. Tapping it opens Timonel and starts recording directly (the voice-first affordance), matching "grabar audio directamente."
- **Record audio inside the panel.** The input row gained a mic button next to the text field. Tapping it toggles a recording bar (pulsing dot, timer, Listo to stop). On stop, a voice-note bubble lands in the thread and Timonel transcribes it ("Entendí: ...") and runs the same confirm-then-receipt flow. So the owner can talk or type, and either way a money write still passes through confirm, receipt and undo.

This makes voice the primary way a non-technical owner operates, which is the point of installing the AI, while keeping the trust floor intact on voice writes.

**Re-dispatched:** none.
**Screenshots:** `screenshots/iter-04-mobile-mic-fab.png`, `screenshots/iter-04-desktop-recording.png`, `screenshots/iter-04-desktop-voicenote.png`.

feel: the mic as the main button says "just talk to it" before a single word is read; recording feels live and reversible, and seeing the spoken sale turn into a written confirmation you can still say no to makes the voice feel safe, not magic.

### Note for /develop (carry-forward)

Real audio needs microphone permission and a speech-to-text path. The mockup simulates the recording state and the transcription; the spec's AC set treats the write trust floor as binding on voice writes exactly as on typed ones, and real speech-to-text plus mic permission handling is called out as its own task in M2/M3.

## Approved — 2026-10-19

**Dario:** "listo"
**Final iter:** 4.
**Mockup files frozen at:** ./mockups/index.html, ./mockups/styles.css, ./mockups/fixture.js
**Carry-forward to /develop:** three tabs (Hoy, Operación, Costos y producción); Timonel collapsed by default with a microphone launcher (voice-first), opening as a right drawer on desktop and a bottom sheet on mobile; voice and typed inputs both pass the confirm, receipt and undo trust floor; every module reachable and editable via tile drill-ins. These visible affordances are binding for the implementation.
