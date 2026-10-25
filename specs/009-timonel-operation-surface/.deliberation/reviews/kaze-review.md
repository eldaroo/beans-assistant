# Kaze — Creative Director of Living Systems

Faculty: how the surface *feels*. On the indigo Beans Command Center identity (kept, not swapped).

## 1. The problem this is actually solving

The owner spoke to Timonel like a person and got a form's answer: `product_not_found`, then "No pude interpretar eso." The wall is not capability — it is **conversational dignity**. The chat looks alive (a floating bubble, a thread) but behaves like a dropdown that rejects you. The real problem: the one write lever in the whole app breaks the moment reality is messy (new product, ambiguous name, a follow-up). We are building the *feeling* that the assistant heard you and is already handling it.

## 2. Smallest first version that proves the idea

M1's compound card, and nothing else. One failed "me entraron 50 pulseras rojas" must return **one card** that reads: *"No tengo 'pulseras rojas'. ¿La creo y sumo 50?"* — a single Confirmar that does both steps, with a quiet "crear producto nuevo · +50 stock" sub-line. If that one moment turns a dead end into a done thing, the whole thesis is proven before any keystone lands.

## 3. Three risks that would kill this

1. **Confirm fatigue.** Every op is a card with the same green Confirmar. Compound + corrections + guided cost = a wall of identical buttons. If a QUERY answer also looks like a card, the owner stops reading and reflex-taps. Reads must have a *calm, button-less shape*; writes must be visually heavier than reads.
2. **The picker as interrogation.** "¿Cuál? 1)… 2)…" typed as numbered text feels like an IVR phone tree. On a phone, typing "2" then waiting is friction. It must be tappable chips, and appear only on true ambiguity — never as a reflex.
3. **M7 guided cost-flow becoming a wizard.** Eight interdependent fields over multi-turn chat can feel like a tax form wearing a chat costume. One wrong-feeling question and the owner abandons and never feeds the cost model again.

## 4. Success at 90 days

The owner never once sees a raw error string. He types one messy sentence per real-world event and watches a card resolve it — often compound, sometimes answered as plain calm text, occasionally a two-tap pick. He trusts Deshacer enough to move fast. He has fed the cost model entirely by chatting, and could not tell you there was ever an "orchestration layer."

## 5. Atomic tasks (each ≤1 day)

- [M1] Compound confirm-card component: one card, stacked steps, single Confirmar, per-step sub-lines.
- [M1] Rewrite `product_not_found` + unparsed copy from error strings to offers ("¿La creo y…?").
- [M2] Disambiguation as tappable chips (not numbered text); show only on >1 match; max ~4 + "ninguna".
- [M4] QUERY render = calm, borderless answer shape, visually distinct from confirm cards; no buttons.
- [M4] Lighten read bubbles / weight write cards so the eye separates "told me" from "will do".
- [M3] Correction cards (cancel/edit) in a warmer/amber accent so a destructive confirm never looks like a create.
- [M5] Follow-up turns render inline under the active flow, not as fresh detached bubbles — show the thread is holding context.
- [M7] Guided cost-flow as a progressive card (one field at a time, running summary, "me faltan 2"), never a Q-and-A volley.
- [M8] Durable receipts strip: last ops with persistent Deshacer surviving refresh; timestamp + plain summary.
- [M1] Busy state: replace "..." with a typing/thinking shimmer so latency feels like listening.

## 6. The one thing only my faculty noticed

**The confirm button is overloaded to death.** Right now *every* outcome — create, compound, cancel, price-change, and soon a read — is the same bordered card with the same emerald "Confirmar." That single visual grammar is the thing that will collapse under the expanded surface. A read is an exhale (no action owed); a create is a nod; a cancel is a caution. If all three wear the identical card, the owner stops *reading* and starts *tapping* — and the propose-only safety spine, which depends entirely on the human actually reading the proposal before confirming, quietly becomes theater. Three shapes, not one: **answer (calm, no button) · create (neutral card, confirm) · undo/cancel (amber, deliberate).** That visual hierarchy is a safety feature, not decoration.
