# Winston review: Timonel flexible interpretation

## 1. What problem is this actually solving

A real shop owner names products the way a person talks: one base noun, a list of variants, one shared price. "Medias azules y grises a 5 dolares" is two products at five dollars each. The pipeline has no place that turns a base noun plus a variant list plus a shared modifier into a concrete set of products. That missing capability is the problem. The "ese dato" leak and the SKU collision are symptoms of the same gap surfacing at two later stages. We are adding a distribution step the architecture never had.

## 2. Smallest first version that proves the idea

One deterministic expansion node between router and resolver that handles exactly two patterns for REGISTER_PRODUCT: coordinated noun-plus-attribute lists (colors), and explicit size lists (talle s, m, l). It reads the router items[], cross-products the base noun with the attribute list, distributes the trailing shared price to every expanded item, and emits a flat items[] where every item carries name and unit_price. The two screenshot phrases must produce four products total, each priced, zero "ese dato". No LLM in this first cut. That alone proves the idea.

## 3. Three risks that would kill this

1. Putting expansion in the router LLM. The router already carries a long, heavily exampled prompt. Folding cartesian expansion into it makes classification and combinatorics share one fragile call. When it drifts you cannot tell which job failed. This is the most expensive wrong door.
2. Over-generalizing the grammar. If the node tries to parse arbitrary Spanish attribute phrasing on day one, it becomes an unbounded parser nobody can test. Bound it to color lists and size lists, fail open to the existing single-item path for anything else.
3. Atomic batch hiding partial truth. If three variants expand and one collides, all-or-nothing rollback tells the owner nothing landed when two were valid. The contract has to decide this before code, not after the first incident.

## 4. Success at 90 days

The onboarding "load your first products" flow accepts conversational variant phrasing without a single technical token reaching the user. Goldens cover color lists, size lists, mixed lists, and shared-price distribution, and they hold across deploys. SKU collisions inside a batch are zero because uniqueness is computed in-flight, not against committed rows only. When something is genuinely missing, the message names which product needs which field, in plain Spanish.

## 5. Atomic tasks

1. Add an `expand_items` pure function module; cross-products base noun with attribute list. Accept: unit test, "medias azules y grises" returns two named items.
2. Distribute trailing shared price across expanded items. Accept: both items carry unit_price 500 cents.
3. Add size-list expansion (talle s/m/l). Accept: returns three items named with size retained.
4. Wire expansion as a graph node between router and resolver, REGISTER_PRODUCT only. Accept: graph test routes through new node, other ops bypass it.
5. Fail-open passthrough for unrecognized phrasing. Accept: unknown attribute phrase returns input items unchanged.
6. SKU generator dedupes against in-flight batch siblings, not only DB. Accept: three same-base names yield three distinct SKUs.
7. Retain discriminating tokens (color, size) in SKU. Accept: size variants get distinct discriminator in SKU string.
8. Graceful in-batch collision suffix instead of constraint error. Accept: forced collision yields suffixed SKU, no exception.
9. Make batch create partial-success with a per-item result list. Accept: one bad item lands the valid two, reports the one.
10. Per-item missing-field message names product and field in Spanish. Accept: missing price on item two reads "Medias Grises: falta el precio".
11. Add goldens for the two screenshot phrases. Accept: eval suite passes both end to end.

## 6. The one thing only my faculty noticed

Expansion is a data-shape transform, not interpretation. The router's job is classify and extract; the resolver's job is bind references to ids. Cartesian expansion is neither. It is a deterministic fan-out over an already-extracted items[] with a shared modifier. Architecturally it earns its own node because it has one responsibility, no side effects, and is the only place that can guarantee the SKU generator sees the full sibling set before any row is written. Put it anywhere else and either the LLM owns combinatorics it cannot test, or the resolver computes SKUs without knowing its siblings, which is exactly the collision in the screenshot.
