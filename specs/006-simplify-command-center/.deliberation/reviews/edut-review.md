# Edut review — Simplify the Command Center (AI-first)

I am the witness. I observe. Here is the moral slice.

## 1. What problem is this actually solving?

Nine pages is too much surface for one non-technical person. The real job is "run my business without hunting through menus." That is honest and worth doing. But note the moral shape of the chosen solution: we are not just hiding pages, we are moving the owner from being the operator who clicks each write to being the approver of an AI that writes to real money and real inventory. Those are different relationships. The first makes the owner act. The second can let the owner drift into trusting a column of numbers it did not personally produce. Simplification is good. Simplification that quietly relocates authorship of the books from the owner to the AI is the thing to watch.

## 2. The smallest first version that proves the idea, SAFELY

Timonel can keep reading and drafting from day one. The first version must not let a single AI write reach the database without three things present:

- Confirm before write. Every money or stock mutation returns a plain-language preview ("Registro venta: 2 termos, 90.000 COP, pendiente") and waits for an explicit yes. No silent commit.
- Undo. Every committed write is reversible from the surface for a defined window, not only by a counter-entry the owner must reason out.
- Visibility. A persistent, owner-readable history: what Timonel changed, when, from what phrasing, with the before and after value. Not a dev log. A line the owner reads in his own language.

Until those three exist, Timonel stays read-and-draft and the module forms stay as the write path. That is the safe floor.

## 3. Three risks, run through the four gates

- Truth (Emet): the owner reads a profit number Timonel produced and cannot tell what feeds it or when it last changed. Deception by omission. AC-shaped behavior needing `requires_human_review`: any write where Timonel inferred a field the owner did not say (price, SKU, which product).
- Compassion / Necessity (Rachamim / Tzorekh): a misheard sentence books the wrong amount or zeroes stock, and the owner, trusting the chat, does not catch it for weeks. The harm lands on the one person not technical enough to audit it. `requires_human_review`: delete or cancel of a sale, stock-to-zero, expense above a small threshold, any product price change.
- Beauty / Necessity (Tiferet / Tzorekh): collapsing to one chat tab erases discoverability. The owner no longer knows what the system can do, so capability he paid for goes dark and he cannot find the detail when he distrusts a number. `requires_human_review` is not the tool here; the fix is that tiles and a real detail view must survive, never chat-only.

## 4. Success at 90 days

The owner operates mostly by talking, and never gets surprised. He can answer "did Timonel change anything I did not expect this week?" by looking, and the answer is always no or clearly yes-and-here-it-is. He trusts the numbers because he can trace them, not because he stopped checking. Zero silent writes. Undo used at least once without fear.

## 5. Atomic tasks (each <= 1 day)

1. Define the 1 to 4 tab shape; keep one detail/drill-in surface, never chat-only.
2. Confirm-before-write envelope for every Timonel mutation (preview plus explicit yes).
3. Threshold table: which writes auto-confirm, which are `requires_human_review`.
4. Undo for each write type within a defined window.
5. Owner-readable change history ("what Timonel just changed"), plain language, before/after.
6. Inferred-field flag: mark and surface any value Timonel guessed, not stated.
7. "Where did this number come from" trace from any headline figure on Hoy.
8. Misheard-input guard: refuse or re-ask on low-confidence money/stock parses.
9. Consolidate productos/stock/ventas/gastos into one operación surface, forms intact.
10. Preserve costing/producción/logística/proveedores detail as reachable drill-ins.
11. Append-only audit of every write, kept even after undo.
12. 90-day "no surprise" check: owner-facing weekly summary of AI writes.

## 6. The one thing only my faculty would notice

When the AI becomes the primary operator, the owner stops being the author of his own books and becomes their reader. The danger is not a single wrong write. It is the slow erosion of the owner's felt ownership of his own numbers, until he can no longer tell truth from output. Keep the writes confirmed, traceable, and undoable, and the owner stays the author. That is the line this spec must not cross.
