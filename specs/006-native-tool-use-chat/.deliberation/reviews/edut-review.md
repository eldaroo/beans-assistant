# Edut review — Beans native-tool-use chat (spec 006)

I observe. I run the four Action Gates on a chat that moves real money and real records.

**Truth (Emet).** The post-write acknowledgement is the honesty surface. The chat must state what it did, with the committed values read back from the API response, not from the model's memory of what it proposed. A write that says "listo" without naming the SKU, the amount, and the new balance hides its effect. That is deception by omission.

**Compassion (Rachamim).** CANCEL_* and DEACTIVATE_PRODUCT are the operations that surprise. The operator asks for one thing in fast Spanish and the model infers a cancellation. The confirm card must show the exact target row (which sale, expense, or product) before commit, never a paraphrase.

**Necessity (Tzorekh).** Native tool-use is binding. The council's job is to make it safe. Every write passes a confirm. No read justifies a silent write. REGISTER_PRODUCTS_BATCH is where confirm fatigue tempts auto-approval. Do not. A batch confirms as a batch, itemized.

**Beauty (Tiferet).** Proportionate means a one-item sale takes one confirm and a twelve-item batch takes one itemized confirm, not twelve taps and not zero.

## The six questions

**1. What problem is this actually solving?**
The operator wants to run the business by talking to it, not by filling forms. The real problem is that Costos, Produccion, Logistica and Proveedores have no write path except the chat. The chat is not a convenience there. It is the only door. That raises the stakes on correctness, not lowers them.

**2. Smallest first version that proves the idea?**
Reads plus the three lowest-harm, fully-reversible writes: REGISTER_SALE, REGISTER_EXPENSE, ADD_STOCK, each behind a read-back confirm card. Prove the loop, the confirm, and the honest acknowledgement before any CANCEL_* or DEACTIVATE_PRODUCT is enabled.

**3. Three risks that would kill this if ignored?**
- Misread number. A model parsing "mil quinientos" or "1.500" against Argentine decimal and thousands conventions writes the wrong amount. The confirm card must show the parsed number in digits for the operator to catch.
- Irreversible writes with a reversible UI. CANCEL and DEACTIVATE feel like undo but may not be. If the operation is not actually reversible, the card must say so in plain words before commit.
- Injection to write. Spec 005's council closed this surface; native tool-use reopens it. A read tool returning tenant text that contains an instruction must never become a write. The confirm gate is the firebreak only if it is never auto-satisfied.

**4. Success at 90 days?**
Zero committed writes the operator did not confirm. Zero wrong-value writes that reached the DB. Every write has a readable audit row naming operator, tool, parsed args, and committed result. The old Timonel is retired with no regressions in the reads.

**5. Atomic tasks.** See the eng and Tamir files for the build breakdown. My required additions: (a) read-back confirm card showing parsed numeric args in digits; (b) irreversibility flag surfaced in the card for CANCEL_* and DEACTIVATE_PRODUCT; (c) acknowledgement rendered from the API commit response, not the proposal; (d) append-only write-intent audit row per confirm and per commit.

**6. The one thing only I would have noticed.**
No confirm gate may be auto-satisfied by model output. The confirm is a human yes. Any code path where the loop confirms its own card is the breach.

**Stamp requires_human_review:** every CANCEL_*, CANCEL_LAST_OPERATION, DEACTIVATE_PRODUCT, and REGISTER_PRODUCTS_BATCH acceptance criterion. These are the irreversible and the bulk surfaces. The witness holds them.

This is not novel territory. I do not call Mar'ah. The four gates hold it.
