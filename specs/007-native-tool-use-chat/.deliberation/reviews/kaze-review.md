# Kaze review — Beans & Co native-tool-use chat (spec 006)

Creative direction. The felt experience of a chat that moves real money.

## 1. What problem is this actually solving?

The owner should run the business by talking to it and never once wonder "did that actually happen." The old Timonel answered. This one acts. The real problem is not routing or models. It is trust at the moment of commit. The design job is to make the half second before a write feel safe, and the moment after it feel settled. Everything else is plumbing.

## 2. Smallest first version that proves the idea

One read and one write, end to end, with the confirm card between them. A stock question returns a clean result with no tool noise. "Registrá una venta" renders a proposed-operation card, waits, commits on confirm, acknowledges exactly what it did, and points to the Ventas tile. If REGISTER_SALE feels honest and reversible, every other write inherits the grammar. Prove the feeling on one write before wiring twelve.

## 3. Three risks that would kill this

- The confirm card looks like the receipt card. If "about to happen" and "happened" share a shape, the operator stops reading and clicks through. Death by habituation on a money surface.
- Tool-loop noise. If the thread narrates every read and every thought, the owner watches a machine work instead of talking to a partner. Reads must be silent. Only results and proposed writes earn a place.
- Confirm fatigue. If a batch of ten products demands ten taps, people learn to tap without looking. One proposal, one confirm, itemized inside.

## 4. Success at 90 days

The owner opens the chat before the tiles. The confirm card is read, not reflexed, because it stays visually distinct from every receipt. Writes land, the matching tile is where attention goes next, and "did it save" has left the owner's behavior. The chat feels like one calm voice, not a pipeline with a face.

## 5. Atomic tasks

1. Define two card shapes as separate visual species: proposed (provisional) and committed (settled). Token work.
2. Add a `proposed-operation` state to the widget state machine, between thinking and committed.
3. Render the proposal card: operation name in plain Spanish, the exact values, Confirmar and Cancelar.
4. Weight transition on confirm: the provisional card settles into the committed receipt in place, 300ms deceleration.
5. Suppress read tool-calls; show results only.
6. Collapse multi-step tool use to a single quiet "Trabajando" status, no per-step chatter.
7. Itemize batch writes inside one proposal card, one confirm for the set.
8. Wire the committed card to the existing `navigation` cue so the right tile follows the write.
9. Undo affordance on cancelable writes (CANCEL_SALE, CANCEL_LAST_OPERATION) as a quiet secondary action.
10. Error state as apology plus path, never a raw code, reusing ERROR_FALLBACK_COPY tone.
11. Mobile pass: proposal card and its buttons thumb-reachable, 44px targets, no horizontal scroll at 360px.

## 6. The one thing only my faculty would have noticed

Today's `tim-toolcard` is a receipt, painted green or red after the fact. Spec 006 reuses it for the confirm step, so a proposal and a completed write will look identical. That collapses the one distinction the whole surface depends on. The proposal must feel unfinished, dashed border, muted, holding its breath. The commit must drop into weight, solid, settled, done. If the operator cannot feel that change of state in their body, the confirm card is theater and the money is unguarded.
