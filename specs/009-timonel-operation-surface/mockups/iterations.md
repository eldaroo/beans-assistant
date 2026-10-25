# Mockup iterations - spec 009 Timonel operation surface

Served locally with Cache-Control no-store. Design pair: Kaze (creative), Sally (UX/IA). Built on the existing Beans Command Center indigo identity (no brand swap).

## Iter 01 - 2026-10-24

First build. Covers the five flows the spec walks: QUERY answer, compound create+act card, disambiguation picker, cancel card, guided cost-flow, settled receipt with Undo. Three response shapes carried on indigo + amber as the safety feature.

### Completion checklist (floor, per genesis-spec Section E)

**E.1 states**
- empty: first-open invitation with three tappable example chips teaching the shapes. feel: opening it feels like an invitation to talk, not a blank form.
- loading: inline indigo shimmer on the answer rail, not a panel spinner. feel: latency feels like Timonel listening, not a freeze.
- populated: a real conversation mixing answer, create, picker, cancel, cost-flow, receipt. feel: the owner sees at a glance what was told versus what will happen.
- error: four distinct calm sub-shapes (parse-fail, validation, no-permission, server-failure) as borderless notes with a next step. feel: a problem reads as a gentle redirection, never a red wall.

**E.2 viewports**
- mobile 390px canonical (default) and desktop 760px via the Pantalla switch. feel: the phone width feels like the real surface the owner uses, one action in view.

**E.3 wired interactions**
- Confirmar on the compound card settles both steps into one receipt; Confirmar on the cancel card settles with the reversal line; picker select stages a price-change card then settles; cost-flow Seguir advances the question and ticks the checklist; Undo reverts a receipt; example chips fill the composer; composer submit echoes the message. feel: every tap produces a visible, legible consequence.

**E.4 affordance cues**
- answer has no button (text only); create has a filled indigo Confirmar plus a ghost Ahora no; cancel has an amber verb-bearing Si, cancelar la venta; picker rows carry a chevron and a listbox role; Undo is a low-contrast underlined link. feel: a destructive card looks heavier than a create card, so it cannot be tapped by reflex.

**E.5 accessibility**
- 2px indigo focus rings, focus order mirrors reading order, 44px minimum touch targets, keyboard activation on all controls, listbox semantics on the picker, prefers-reduced-motion disables the shimmer animation, dark mode via prefers-color-scheme and the Tema switch with amber legible on dark, indigo and ink contrast held at or above WCAG AA. feel: the surface is as usable by thumb and keyboard at night as by mouse in daylight.

### Kaze + Sally free-form note (E.7)

Alive: the three-shape ladder (answer lighter than create lighter than cancel) does the safety work visually, so the propose-only spine is felt, not just enforced. The compound card telling the owner both effects in one place is the exact heal for the screenshot dead end. Dead: nothing bloated yet; the cost-flow card is the one at risk of feeling like a form if its questions stack, so it stays one field at a time with a running checklist. One cut before the next vuelta: keep the cancel consequence to a single sentence so the amber card never becomes a wall of text.

Screenshot: live walk at http://127.0.0.1:4186/ (Dario is at his machine).

## Approved - 2026-10-24

Dario: "perfectoo, dame el develop headless command para drenar todo junto"
Final iter: 1.
Mockup files frozen at: ./index.html, ./styles.css, ./fixture.js
Carry-forward to /develop: any visible affordance in the approved mockup is binding for the implementation. T-000 ports it into the chat surface as the first task; the three response shapes and the compound/picker/cost-flow cards are the visual contract.
