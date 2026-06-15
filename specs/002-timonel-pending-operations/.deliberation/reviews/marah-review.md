# Mar'ah (Mirrorblade) — adversarial review

*The mirror reveals; the blade cuts the concealment; what is hidden is hidden no more.*

I do not design this feature. I try to make it write a false sale into a tenant's books, then I name the guard that stops me. Every attack below is a sequence the acceptance criteria must defend against.

## 1. What problem is this actually solving

A paused write is a half-truth held in conversation. The danger is not losing it; it is resuming it against the wrong fact. The real problem is binding a later free-text reply to the correct paused operation, or refusing.

## 2. Smallest first version that proves it

One operation type only: REGISTER_SALE paused on `unit_price`. Single active pending op. A typed reply that supplies the price resumes the exact stored product and quantity, asks one confirmation, then records once. Everything else re-asks. If that one path cannot be made safe, nothing else should ship.

## 3. The risks that kill this

1. **Silent mis-binding.** A bare number resumes a stale or wrong operation, recording a false sale. This is the whole risk; the rest are its faces.
2. **Double-record.** Resume runs without an idempotency key, network retry posts the sale twice.
3. **Guess-on-ambiguity.** The machine completes when it should re-ask, hiding its uncertainty behind a confident write.

## ATTACK CASES (each becomes an acceptance criterion)

- **A1 — detour question.** Pause sale for price, user sends "cuanto stock tengo". *Guard: pending op survives a read-only detour; only a reply that parses as the missing field resumes it. AC: an interleaved read intent does not consume or clear the pending op, and a bare number arriving after a non-price turn does not auto-resume without re-confirmation.*
- **A2 — stacked pendings.** User starts a sale, then a stock-add, both missing a field; next reply has one number. *Guard: single-active-pending. AC: at most one pending op exists; starting a second pauses or replaces the first explicitly, and the resume names which op it completes before writing.*
- **A3 — wrong-product price.** "32 usd" meant a different product than the paused one. *Guard: confirmation echo. AC: resume restates product + quantity + price ("Stanley x40 a 32 usd, confirmás?") and writes only on an affirmative.*
- **A4 — retry double-send.** Price reply sent twice. *Guard: idempotency key. AC: the resumed sale carries a deterministic key (tenant, product, qty, pending-op-id); a second completion with the same key is a no-op, verified by one ledger row.*
- **A5 — stale resurrection.** Pending op is 10 minutes old, user moved on, a later unrelated number revives it. *Guard: TTL. AC: a pending op older than N minutes (proposed 3) is expired and cannot be resumed; a number after expiry re-classifies cold.*
- **A6 — cancel without number.** Reply is "no, dejá". *Guard: explicit-cancel parse runs before field extraction. AC: a reply matching cancel intent clears the pending op and writes nothing, even though it contains no number.*
- **A7 — number that is not a price.** "son 40" or a quantity restatement. *Guard: typed-field validation. AC: the extracted value must validate as the specific missing field type; a failed parse re-asks, never writes.*

## 5. Tasks (guards + replay regressions)

1. Pending-op store: typed record (op-type, product-id, qty, missing-field, created-at, op-id).
2. Single-active-pending enforcement on write.
3. TTL expiry sweep + cold re-classify on expired.
4. Explicit-cancel parse ahead of field extraction.
5. Typed-field validator for the missing field.
6. Confirmation-echo gate before any resumed write.
7. Idempotency key on resume; no-op on duplicate.
8. Regression suite replaying A1 through A7, each asserting exactly zero or one ledger row.

## 6. The one thing only I noticed

The bare-number detector is the blade pointed at the tenant's books. Without a TTL and a confirmation echo, "32" three turns later silently writes a sale nobody asked for. Most dangerous case: **A5/A1, a stale or post-detour bare number auto-resuming the wrong sale; the guard is TTL expiry plus a mandatory confirmation echo.**
