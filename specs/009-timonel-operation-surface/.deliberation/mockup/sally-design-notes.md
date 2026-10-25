# Sally — UX design notes: Timonel operation surface (Beans spec 009)

The app is read-only; this chat is the only lever that writes or corrects. So every turn must make the *effect* legible before the hand moves. Design to that.

## Reading order inside a turn
Each assistant turn is a card read top-to-bottom as **Effect → Detail → Action**.
1. **Effect line** (first, largest, 15px/600): the plain consequence in the owner's words — "Venta: 40 Stanley a 32" / "Vas a cancelar la venta de Juan (devuelve 2 al stock)". Reversed stock and reverted price belong here, not buried.
2. **Detail** (14px, muted indigo-slate): sku, resolved id echoed as human name, derived figures (USD the app computed, flagged "calculado"). Never an opaque op_token.
3. **Action** (last): buttons, or none. The owner must have read the effect before reaching the control.

For a compound card (create-then-act), render the two steps as an ordered 1→2 list, each with its own effect line and its own settle state, so "crear producto" visibly precedes "+50 stock" and the created id threads down.

## Four mandatory states
- **Empty (first open):** one warm bot line plus 3 tappable example chips ("vendí 40 stanleys a 32", "cuánto vendí hoy", "me entraron 50 rojas"). The chips teach the three response shapes exist. Input autofocused, placeholder "Escribí una operación o preguntá…". No scary disclaimer.
- **Loading:** keep the user bubble, append a quiet bot row with a 3-dot indigo shimmer and label "interpretando…" (parse) / "preparando…" (staging). No spinner on the whole panel; the thread stays readable.
- **Populated:** a mixed thread — answer rows (no card chrome), create cards (neutral), cancel/undo cards (amber). Settled cards collapse to a one-line receipt ("Hecho ✓") so history stays scannable; only the live card shows full detail.
- **Error:** four distinct shapes, never a red toast. Parse-fail = calm bot line + "probá así:" example, never "no pude interpretar" as a dead end. Product-not-found = **not an error** — it becomes the compound create-then-act card. Server failure = inline bot row, amber dot, "reintentar" button, card stays pending. No-permission = plain bot line stating who can do it; no button.

## Affordance cues (so no reflex tap)
- **Answer:** text only, no border, no button. Nothing to tap, nothing to fear.
- **Create (Confirmar/Cancelar):** neutral card, hairline indigo border. Confirmar = filled indigo (primary weight); Cancelar = ghost/outline. Equal size, 12px gap, Confirmar on the left but *not* pre-focused.
- **Cancel/Undo (destructive):** amber card wash + amber border + a small ⚠ glyph on the effect line. The confirm button is amber-outlined, label carries the verb ("Sí, cancelar la venta") — never a bare "Confirmar". Deliberate by look.
- **Disambiguation picker:** rendered as a vertical list of chevron rows (chevron = tappable), each with the resolved name + date + amount, hover/active indigo tint, full-row hit area. Reads as a menu, not a message.
- **Undo on a settled receipt:** a quiet text link "deshacer" on the receipt line, low-contrast until focus/hover brings it up. Discoverable on scan, not fat-fingered. Confirm step on undo of anything irreversible.

## Accessibility floor
Focus order = reading order (effect→detail→buttons), newest card focused on arrival. All touch targets ≥44px (pad the small undo/× links to hit area even when visually light). Enter/Space activate every button and picker row; the picker is a real radio/listbox, arrow-navigable. Visible 2px indigo focus ring on everything, offset for contrast. `prefers-reduced-motion`: drop the shimmer/slide, keep instant state swaps. Dark mode: deepen the indigo, keep amber legible on dark (amber-300 on amber-950). Hold indigo text ≥4.5:1 on its surface; the filled-indigo button needs white text ≥4.5:1 — darken the indigo if it fails.

## Anti-patterns for this surface
No auto-posting a destructive/cost op (registry human-review is permanent — the UI must never imply otherwise). No identical Confirmar button across create and cancel (Kaze's overload — the whole safety spine goes theater). No destructive confirm pre-focused or Enter-defaulted. No modal over the thread. No red error walls where a next-step card belongs. No showing op_tokens, raw ids, or model JSON. No optimistic "Hecho" before the server confirms.
