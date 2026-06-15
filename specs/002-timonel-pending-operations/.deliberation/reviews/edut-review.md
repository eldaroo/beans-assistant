# Edut review — Timonel deferred-operation completion

I am the witness. This feature auto-completes a financial write from a one-word reply. I observe the consent and truth seams.

## 1. What problem is this actually solving?

The user states a sale, the bot pauses for a price, the user supplies it, and the system loses the operation. The real problem is not memory. It is that resuming a paused write means the system finishes a money record on the user's behalf from fragmentary input. The problem worth solving is doing that without recording a sale the user did not mean.

## 2. What is the smallest first version that proves the idea?

REGISTER_SALE paused on missing unit_price only. The reply fills the price and the system writes the sale. Prove it with one operation type, a confirmation gate, and a cancel path. Do not generalize to other paused operations until the gate and cancel are proven on this one.

## 3. What 3 risks would kill this if ignored?

- A wrong guess writes a real sale into a tenant's books. "32 usd" could mean unit price, total, or a new product. Guessing is harm, not a bug.
- Silent completion. The bot writes and the user never gets a clear statement of exactly what was recorded, so a wrong record sits undetected.
- Cancel that leaves residue. The user says olvidá and a pending row, or a half-written sale, survives.

## 4. What does success look like at 90 days?

Zero sales recorded that the user later disputes as never-intended. Every resumed write was either confirmed or cleanly reversible. Every cancel left no trace. The audit log shows, for each completed sale, the turn that triggered it and the exact figures written.

## Confirmation: proportionate answer

A clear after-the-fact statement is not enough on a money write. The reply "32 usd" is ambiguous on its face. Before writing, Timonel must confirm: registro la venta de 40 Termos Stanley a 32, total 1280, dale? Then write on yes. The cost of confirming is one turn. The cost of not confirming is a wrong financial record in someone else's books. Proportion favors the gate. After-the-fact statements are the fallback only when the reply was unambiguous and the operation reversible, never the default.

When an ambiguous reply is guessed wrong and a sale is recorded the user did not mean, trust does not erode slowly. It breaks at once. The user stops trusting the assistant near their books, which is the one place trust is the whole product.

Emet: the completion copy must describe exactly what was written and never more. No "listo, registrado" that implies more than the row holds. If only price and sale were written, say only that.

The olvidá / cancelá escape: the user must abandon a pending operation in plain language and trust it left no trace. Cancel clears the pending state and writes nothing. If a write already happened, cancel reverses it and says so plainly.

## 5. Moral-guard tasks

- Confirmation gate: before any resumed write, emit a confirmation naming product, quantity, unit price, and total; write only on explicit yes. Acceptance: a paused sale resumed with an ambiguous price reply produces a confirmation prompt and zero DB write until the user confirms.
- Cancel path: olvidá / cancelá / no abandons the pending operation. Acceptance: after cancel, the pending store holds no entry and no sale row exists for that detour.
- Truthful completion copy: the success message states exactly the figures written, nothing implied beyond. Acceptance: completion copy fields equal the persisted row fields, asserted in test.
- Audit line: every resumed completion logs the trigger turn and exact figures. Acceptance: each auto-completed sale has one audit entry naming trigger turn, product, quantity, price, total.

## 6. The one thing only my faculty noticed

Idempotency protects against double-writing the right sale. It does nothing against writing the wrong sale once. The whole moral surface lives in the single write the system was confident about.

Summary: the panel must not ship this without a confirmation gate before any auto-completed sale write.
