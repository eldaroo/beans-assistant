# Kaze — Mockup Design Notes: Timonel chat surface

For the self-contained HTML/CSS mockup. Built ON the Beans Command Center indigo identity (`indigo-600` primary, `indigo-50`/`indigo-100` tints, `slate` neutrals). No brand swap.

## Atmosphere & density
Phone-first. The owner is behind a counter, one thumb, interrupted. The thread breathes: generous `12px` vertical gap between turns, `16px` side gutter, `15px` base text, `1.5` line-height. One action in view at a time — never two live cards competing. The panel is calm slate-white (`#fff` / `slate-50` tint), not a busy dashboard. Latency reads as *listening*: replace the `...` with a three-dot indigo shimmer (`indigo-400`, 1.2s pulse), so waiting feels like the assistant heard you.

## Three response shapes — the load-bearing safety feature
The confirm button is overloaded today; one grammar for read, create, and cancel turns reading into reflex-tapping and the propose-only spine into theater. Three visually distinct shapes:

1. **Answer (read) — calm, borderless, no button.** A soft exhale. No card frame, no border, no action. `slate-700` text on transparent or faintest `slate-50`, left-aligned, `15px`, normal weight. A thin `indigo-200` left rule (`border-l-2`, `pl-3`) marks it as Timonel speaking. Nothing is owed; the eye relaxes.
2. **Create — neutral card, single Confirmar.** A quiet nod. White card, `1px solid slate-200`, `rounded-xl`, `12px` padding, soft shadow. Effect summary in `slate-900 font-medium`, a muted `slate-500 text-xs` sub-line (`crear producto nuevo · +50 stock`). One **`indigo-600`** `Confirmar` (`font-medium`, `rounded-lg`, full-ish width) + a text-only `Cancelar` in `slate-400`. Weight sits clearly above a read.
3. **Undo-or-cancel (destructive) — amber, deliberate, full consequence.** A caution, never a create. Card tinted `amber-50`, `1px solid amber-300`, an `amber-700` heading. It shows the *whole* reversal before confirm: `Se revierte: +12 medias al stock · venta #1842 anulada`. The confirm is `amber-600` and reads `Sí, cancelar la venta` — a sentence, not a bare "Confirmar" — so it cannot be muscle-memory tapped. Deliberate spacing: more padding, the button lower.

## Compound create+act — ONE card, two steps, ONE Confirmar
Not two cards. A single create-shape card with an ordered stepped body: `1. Crear "pulseras rojas"` / `2. Sumar 50 al stock`, each on its own row with a small indigo numeral chip (`indigo-100` bg, `indigo-700` text) and a `slate-500` sub-line. One `Confirmar` at the bottom commits both in order. The visual promise: *I'll handle the whole thing, in this order, on one tap.*

## Disambiguation — tappable chips, never an IVR list
No `1) … 2) …` numbered text. A short prompt (`¿Cuál medias?`) then a horizontal wrap of tap targets: pill chips, `rounded-full`, `slate-100` bg, `slate-800` text, `44px` min height, `8px` gaps, active-press to `indigo-100`. Max ~4 + a `slate-400` outline `ninguna` chip. Appears only on true ambiguity.

## Guided cost-flow — progressive, one field at a time
Not a tax form. A single persistent card that asks **one** question (`¿Cuánto costó el material?`), one input, one accumulating summary above it: a running checklist where answered fields show `slate-700` with a value and pending ones show `slate-400 · pendiente`. A quiet `Me faltan 2` footer. The owner answers, the field fills in place, the next question slides up — momentum, never a wall of fields.

## Effortless / cut
**Keep effortless:** typing one messy sentence and watching a card resolve it; big thumb targets (`44px`+); one decision per screen; Deshacer always one tap away.
**Cut:** numbered-list pickers; any raw error string (offer, don't reject); dual live cards; dense field grids; a second emerald accent (indigo + amber carry everything — a read owes nothing, a create nods, a cancel warns).
