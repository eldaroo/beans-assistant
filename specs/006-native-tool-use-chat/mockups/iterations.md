# Mockup iterations — spec 006 native-tool-use chat

The mockup is the chat surface inside the Beans command center. Design pair: Kaze (creative) and Sally (UX/IA). Served at http://127.0.0.1:4186/ (vanilla HTML + CSS + ES module, ports forward as the implementation seed).

## Iter 01 — 2026-10-17 (first serve)

First synthesis from Kaze's panel review and Sally's design note. The load-bearing move is two visual species: a proposed operation (provisional, dashed, holding its breath) versus a committed receipt (settled, solid). The demo toolbar walks every state; Confirmar on any proposal morphs it in place into the receipt.

### Checklist (E.1 to E.5), each with a feel clause

**E.1 States**
- empty: greeting plus three suggestion chips. feel: the empty state feels like an invitation to speak, not an error screen.
- working: one quiet "Trabajando" row with pulsing dots, replacing per-step tool chatter. feel: the agent feels like it is listening, not like a machine narrating itself.
- populated (read answer and a multi-turn conversation scene): plain assistant bubbles, no tool labels. feel: a read feels like a calm answer from a partner, not a query result.
- error: apology plus a path, incident id muted. feel: the error feels like help, not a stack trace.
  - Note on the three-volume mandate: a chat thread has no row table. Volume is shown as empty, a single-answer turn, and a scrolled multi-turn conversation ending in a proposal. The surface caps at the visible conversation window by design; there is no 5000-row state to show.

**E.2 Viewports**
- mobile 360px canonical (the frame is 380px max, content holds at 360). desktop widens the frame to 400px. feel: the mobile card feels thumb-sized and whole, the desktop feels unchanged, not stretched.

**E.3 Wired interactions**
- Confirmar commits (morph to receipt), Cancelar dismisses with a plain "no registre nada", chips and send drive the working-to-proposal flow, Enter confirms, Escape cancels. feel: confirming feels like a deliberate yes, not a reflex.

**E.4 Affordance cues**
- Confirmar is a filled primary button, Cancelar a subordinate text button (never equal weight to the money action), "Ver en Ventas" is a link, "Deshacer" a quiet secondary button on cancelable writes, "No se puede deshacer" shown on irreversible ones. feel: the eye lands on Confirmar as the weighted choice, and the irreversible warning feels like a hand on the shoulder.

**E.5 Accessibility**
- focus moves to Confirmar on render, tab order follows reading order, 44px targets, prefers-reduced-motion drops the morph for an instant swap, ARIA roles (group for the proposal, status for receipt and working, alert for error, log for the thread), dark mode via semantic tokens at a 4.5:1 floor. feel: operated by keyboard or at night, the surface feels the same calm, nothing lost.

### E.7 free-form note (Kaze + Sally)

What is alive: the two card species read as genuinely different objects, so a proposal cannot be mistaken for a done deal; the silent read keeps the thread quiet enough to feel like a conversation; the amounts in digits on the proposal are the one place the eye checks before a yes. What is dead if we are not careful: the demo toolbar is scaffolding, not product, and must not leak into the real surface; the settle morph must stay subtle, a settling not a bounce, or it turns the money moment into theater. One cut prescribed before the next vuelta: do not add a second accent color for the receipt beyond the green; the calm depends on one voice.

### Open for Dario at the walk-through

- The assistant is named Timonel in the current codebase and slot. The old brain is being retired, but the name can stay or change. Cosmetic, one-line change either way. Pending Dario's call.
