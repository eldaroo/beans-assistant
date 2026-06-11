# Mar'ah (Mirrorblade) review — Truth gate (Emet)

The mirror reveals; the blade cuts the concealment; what is hidden is hidden no more.

My single concern: the words the bot speaks must match the rows in the owner's catalog. Expansion multiplies the ways those two can silently diverge.

## 1. What problem is this actually solving?

Two truth failures, not one interpretation failure. First, the bot refuses real input it could honor. Second, when it does act on multiple products, it cannot yet tell the owner truthfully what landed. RC3 today produces the worst class of lie: "Ningun producto fue creado" when the rollback genuinely created nothing, but the owner reads it as "the bot is broken" rather than "your names collided." The real problem is that the bot's report and the database state are not provably the same fact.

## 2. Smallest first version that proves the idea

Deterministic color-list expansion ("X azules y grises a $5") into two concrete products, each created with its own SKU, and a confirmation that names every product, its SKU, and its price back to the owner before or right after the write. If the smallest version expands but still says "listo," it has proved nothing I care about.

## 3. Three risks that would kill this

- Silent divergence: the summary lists three products but the batch only wrote two, or wrote different names than spoken. A summary built from the input intent rather than the returned DB rows will lie the moment they differ.
- Shared-price mishearing locked in: "$10 para todas" distributed across S, M, L with no confirmation means a mis-parse becomes three wrong prices the owner never sees.
- Duplicate-on-resend: owner re-sends after a partial failure, expansion re-creates the variants that already landed, catalog now holds doubles. No idempotency key today.

## 4. Success at 90 days

Every multi-product turn ends with a report the owner can audit line by line against the catalog: each product named, its SKU, its price. Zero "ese dato" leaks. Zero turns where the spoken count differs from the row count without the bot saying so. Partial successes told precisely, never rounded to all or nothing.

## 5. Atomic tasks

1. Summary is built from returned DB rows (sku, name, stored price_cents), never from input entities — verify: forced name mismatch surfaces in the message.
2. Within-batch partial result: report exactly which products are in the catalog and which are not — verify: 2-of-3 land, message names the 2 created with SKUs and the 1 rejected with reason, never "ningun producto."
3. Confirm a distributed shared price back before commit — verify: "$5 para todas" echoes "Medias Azules $5, Medias Grises $5" and waits for assent on counts above N.
4. Idempotency on resend: same owner, same expanded set within a short window does not duplicate — verify: identical message twice yields one set, second reply says "ya estaban cargadas."
5. Translate indexed missing-field names to "<producto>: falta <campo>" — verify: missing price on variant two reads "Medias Grises: falta el precio," not "ese dato."
6. Golden eval asserting spoken product count equals committed row count for every expansion case — verify: eval fails if they diverge.

## 6. The one thing only the Truth gate would have noticed

`_build_aggregated_summary` (graph.py:162) reconciles truth at the **sub-input** level only. One sub-input that expands to three products is a single success-or-fail unit. So a batch where two variants land and one collides will, after the SKU fix makes the batch non-atomic, report as one failed sub-input and erase the two that succeeded — or one success that hides the one that did not. The expansion fix must push partial-success reporting **down into the batch result**, returning per-product outcomes from `register_products_batch`, or the aggregation layer above it will keep flattening three facts into one and the owner will trust a catalog he cannot see.
