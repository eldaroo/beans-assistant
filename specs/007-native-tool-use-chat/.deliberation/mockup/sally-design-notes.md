# Sally UX note: Beans & Co native-tool-use chat

Grounded in the live `_timonel_slot.html` shell and its tokens (`--card --line --text --muted --accent --good --danger --bg`). Assistant is Timonel. Copy is es-AR, plain, no dashes, no hype, no emojis, no exclamation marks. Canonical 360px, desktop enhancement. Fixtures live in Beans: pulseras de cafe, SKUs, ventas, gastos, stock.

## Reading order per state

One vertical thread, newest at bottom, each state reads top to bottom.

- EMPTY: centered. Title "Tu negocio, anotado y al dia." then "Pedile lo que necesites: stock, ventas, gastos." then 3 suggestion chips. Keep the existing `.tim-empty`.
- WORKING: one quiet row `.tim-working`, text "Trabajando" plus three pulsing dots. One status for the whole tool loop, replaced in place by the answer. Never one row per read.
- READ ANSWER: a plain assistant bubble. "Te quedan 48 Pulsera Cafe Clasica (PCC-001) en stock." No card, no tool label.
- PROPOSED card: reads name first, then values, then actions. Heading "Registrar venta" (eyebrow "Propuesta"), body lines "Producto: Pulsera Cafe Tostado (PCT-002)", "Cantidad: 3", "Total: 10.500", then Confirmar and Cancelar.
- COMMITTED receipt: eyebrow "Registrado", "Venta registrada", "Pulsera Cafe Tostado por 10.500", "Saldo del dia: 128.400", then the tile cue "Ver en Ventas" and, on cancelable writes, a quiet "Deshacer".
- ERROR: apology plus path, never a code. Reuse `error_copy.py` tone: "No reconoci el producto. Decime el nombre exacto." The incident id stays in a muted `.tim-incident` line, not the headline.

## The load-bearing split

Proposed and committed are two species, never one card recolored.

- Proposed `.tim-propose`: dashed 1.5px `--line` border, `--bg` fill, muted heading, visible Confirmar (filled `--accent`) and Cancelar (text button). Unfinished, holding its breath.
- Committed `.tim-receipt`: solid border `--good`, soft `--good-soft` fill, a settled check glyph, no Confirmar. Done.

Retire the shared `.tim-toolcard` green/red paint for writes; it is a receipt and must not serve the proposal.

## Affordances

Confirmar and Cancelar are real `<button>`s, side by side at 360px (Confirmar left-leading as primary, both full-width stacked if the card is narrow). Cancelar is a text button, visually subordinate, so the money action is never a mis-tap of equal weight. "Ver en Ventas" is a link (it navigates via the existing `navigation` cue). "Deshacer" is a quiet secondary button inside the receipt, present only on CANCEL_SALE and CANCEL_LAST_OPERATION. Irreversible ops (CANCEL_*, DEACTIVATE_PRODUCT) show a muted "No se puede deshacer" line above the buttons.

## Batch

One proposal card lists every item as rows ("1. Pulsera Cafe Clasica x12", "2. Pulsera Cafe Miel x8"), one subtotal, one Confirmar for the set. Never N taps.

## Keyboard, focus, touch

Tab order follows reading order: card body is not a tab stop, then Confirmar, then Cancelar. On render move focus to Confirmar. Enter confirms, Escape triggers Cancelar. All of Confirmar, Cancelar, Deshacer, chips, send are at least 44px tall. No horizontal scroll at 360px.

## Motion

The proposal-to-committed weight settle is a 300ms ease-out in-place morph. Under `prefers-reduced-motion`, no morph: the proposal is replaced instantly by the receipt, same final state.

## ARIA

Proposal card `role="group"` with `aria-label="Propuesta de operacion"`; Confirmar/Cancelar inside. Receipt `role="status"`. Working row `role="status" aria-live="polite"` text "Trabajando". Error `role="alert"`. Thread stays `role="log"`.

## Dark mode

Use only semantic tokens; both species must clear 4.5:1 in dark. Dashed proposal border stays visible against dark `--bg`; darken `--good` text token in dark so the receipt is not neon.

## Anti-patterns

No per-step tool chatter. No proposal and receipt sharing a shape or color. No raw code in errors. No color-only state. No Cancelar styled equal to Confirmar. No batch asking per item.
