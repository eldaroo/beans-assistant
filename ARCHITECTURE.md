---
name: timonel-architecture
last_spec: timonel-flexible-interpretation
created: 2026-06-11
mode: create
author: Winston (BuildOS Architect, architecture-author role)
---

# Architecture: Timonel interpretation and orchestration

> The decision log for the Timonel pipeline. The spec is the what and why; this file is why this shape, not the others.

## System shape

Timonel is a LangGraph pipeline over a shared TypedDict state. Each turn flows decomposer to router to one of two arms (read, or resolver then write then optional read), then final_answer, with a sub-input loop for multi-intent turns. Today the pipeline can split a multi-action message and classify each action, but it has no step that turns a base noun plus a coordinated attribute list plus a shared modifier into a concrete set of products. This spec adds exactly one new module, a deterministic expansion node between router and resolver, and tightens two existing contracts (SKU generation in resolver, batch create in database). Every other boundary is preserved.

```
decomposer -> router -> [ read
                        | expander -> resolver -> write -> read? ]
                        -> final_answer -> (advance sub-input | END)
```

Modules in this system:

| Name | Responsibility | Owns |
|------|----------------|------|
| decomposer | split multi-intent turn into sub-inputs | sub_input_queue, cursor |
| router | classify intent and operation, extract items[] | intent, operation_type, normalized_entities |
| expander (new) | fan out base noun x attribute list, distribute shared price | the expanded flat items[] |
| resolver | bind product refs to ids, validate, generate SKUs | normalized product_id, SKU, missing_fields |
| write_agent | execute DB ops, build Spanish summary | operation_result |
| database | atomic-or-partial batch helpers | committed rows |
| graph | wiring, final_answer, missing-field translation | final_answer |

## Decision log

### D-001: Attribute expansion lives in a dedicated node between router and resolver

- **Chosen.** A new deterministic node `expander`, REGISTER_PRODUCT only, reads router items[] and emits a flat expanded items[] before the resolver runs.
- **Alternatives considered.** (a) decomposer splits the phrase into sub-inputs; (b) router LLM emits a fully expanded items[]; (d) resolver expands.
- **Why this won.** Expansion is a data-shape fan-out, not interpretation and not reference binding. It has one responsibility and no side effects, so it is independently testable. It is also the only place that can hand the SKU generator the full sibling set before any row is written, which is the precise condition the collision needs.
- **Why the alternatives lost.** (a) The decomposer works on raw text before classification, so it cannot know an action is REGISTER_PRODUCT or which tokens are a price versus an attribute; distributing a shared price across siblings would mean re-implementing extraction. (b) The router prompt is already long and exampled; folding combinatorics into the classify-and-extract call makes one fragile call own two jobs, and a drift in either is undiagnosable. (d) The resolver binds refs to ids one item at a time; expanding there means siblings are computed mid-resolution and the SKU generator still lacks the full set unless we reorder the resolver internally, which is a bigger change than a clean node.
- **Implications.** Router contract gets simpler, not larger: it emits the base noun, the attribute list, and the shared modifiers, and stops there. The graph gains one conditional edge. Read and non-product write paths bypass the node entirely.
- **Panel source.** Winston. Dissent logged: Lattice, Amelia and Bob favored the decomposer placement (one fewer node, no risk of fighting the router AMBIGUOUS path). Tracked as spec Open Question OQ1, resolved at /develop M1.

### D-002: Expansion is deterministic, LLM only as a fallback

- **Chosen.** Color lists and size lists are expanded by a pure function. The LLM is used only when the router flags the attribute phrasing as genuinely ambiguous.
- **Alternatives considered.** Always-LLM expansion; always-deterministic with hard failure on unknown grammar.
- **Why this won.** The grammar that matters here is regular: a noun followed by a coordinated list joined by commas and "y", with one trailing price. Deterministic code is testable, free, and cannot hallucinate a product.
- **Why the alternatives lost.** Always-LLM adds cost and a hallucination surface to the most common case. Hard-failing on unknown grammar regresses turns the system handles today.
- **Implications.** The node fails open: anything it does not recognize passes through unchanged to the resolver as the existing single-item path. No turn gets worse than today.
- **Panel source.** Winston, grounded in the cheap-LLM cost constraint.

### D-003: Shared modifier (price) distributes at expansion time

- **Chosen.** The trailing shared price is attached to every expanded sibling inside the expander, in cents, before resolution.
- **Alternatives considered.** Distribute in the resolver during validation; leave price on a parent object and have write_agent fan it out.
- **Why this won.** The expander is the one node that holds both the sibling set and the shared modifier in the same scope. Distributing there means every downstream node sees uniform, complete items and never has to reason about a parent-child price relationship.
- **Why the alternatives lost.** Resolver distribution couples validation to expansion semantics. A parent-price object leaks a second shape into write_agent and the summary builder.
- **Implications.** Price stays nullable: an item with no shared price expands to siblings each with unit_price None, and the existing precio-pendiente path handles them.
- **Panel source.** Winston.

### D-004: SKU uniqueness is computed within the batch, with token retention

- **Chosen.** `generate_sku_from_name` dedupes against in-flight siblings AND committed rows, and the generator retains discriminating tokens (color, size) rather than dropping single-letter size tokens.
- **Alternatives considered.** Keep DB-only dedup and let the constraint catch collisions; push uniqueness entirely into the DB with a retry loop.
- **Why this won.** The collision in the screenshot is three siblings sharing a base SKU because none exist in the DB yet. Uniqueness must see the batch as a set. Retaining size and color tokens is what makes the base distinct in the first place, so dedup becomes the rare fallback rather than the rule.
- **Why the alternatives lost.** DB-only dedup is exactly the current bug. A DB retry loop hides a generator that produces colliding names and adds write amplification.
- **Implications.** The generator signature gains the in-flight sibling set. Size tokens that are single letters are no longer skipped when they are the discriminator.
- **Panel source.** Winston, Amelia, Lattice.

### D-005: Batch create degrades to partial success

- **Chosen.** `register_products_batch` lands every valid item and returns a per-item result list. It no longer rolls back the whole turn on one bad row.
- **Alternatives considered.** Keep atomic all-or-nothing; atomic with a pre-flight validation pass that rejects the whole batch on any invalid item.
- **Why this won.** "Cargue dos de tres, falta el precio de Medias Grises" is honest and useful. All-or-nothing tells the owner nothing landed when two were valid, which is the screenshot's second failure dressed differently.
- **Why the alternatives lost.** Atomic is the current behavior and it punishes the owner for a single missing field. A pre-flight reject still loses the valid work.
- **Implications.** write_agent and final_answer must aggregate a per-item outcome list, not a single success or error. This is the larger downstream change and ships behind goldens in M2.
- **Panel source.** Winston, Mar'ah.

### D-006: Missing-field messages name product and field, never indices

- **Chosen.** The resolver attaches structured per-item missing fields carrying the product name and the human field name; graph and write_agent translate from that structure, never from `items[i].field`.
- **Alternatives considered.** Extend the flat translation table to cover indexed names; suppress the index and emit a generic count.
- **Why this won.** "ese dato" is the flat table hitting an indexed key it cannot translate. Carrying the name and field in the structure removes the fallback path entirely and produces "Medias Grises: falta el precio".
- **Why the alternatives lost.** Translating indexed keys is brittle and grows with every operation. A generic count tells the owner nothing actionable.
- **Implications.** missing_fields stops being a list of strings for the multi-product path and becomes a list of {product, field}. Single-item paths keep their flat shape; the translator handles both. The two duplicated translation tables (write_agent.py, graph.py) collapse into one `agents/field_labels.py`.
- **Panel source.** Winston, Amelia, Mar'ah.

## Conventions

- **Naming.** New modules `agents/expander.py` (factory `create_expander_node`, pure helper `expand_items`) and `agents/attributes.py` (the single color and size vocabularies). SKUs stay `BC-{TYPE}-{DESCRIPTORS}` with discriminating tokens retained.
- **Structure.** Expansion logic is a pure function plus a thin node wrapper, mirroring decomposer's `should_decompose` plus `decompose` split. Unit tests live beside existing agent tests; goldens go in tests/eval.
- **Single vocabulary.** Colors and sizes are defined once in `agents/attributes.py` and imported by both the expander and the resolver's `VARIANT_HINT_TOKENS`. No second literal list.
- **Error handling.** Every new node fails open to the existing single-item path. No new node may raise into the graph; on any internal failure it returns the input items unchanged.
- **One writer per fact.** The expander owns the desired product set; the resolver owns reconciliation against catalog state; the database owns committed rows. The summary is built from returned database rows, never from input intent.
- **Observability.** The expander emits one assistant breadcrumb message per turn it acts on, in the decomposer's `[Expander] expanded N items` style.

## Non-goals

- No arbitrary natural-language attribute parsing. Only color lists and size lists in v1; everything else passes through.
- No new operation types. Expansion serves REGISTER_PRODUCT and REGISTER_PRODUCT_WITH_STOCK only.
- No change to the chat widget, channels, auth, or multi-tenant infra.
- No cross-turn memory of variant sets.

## Open architectural questions

- **A-Q1.** Should expansion also serve sales ("vendi 5 medias azules y grises")? Disagreement: clean single-purpose node now versus a general fan-out. Fallback: ship REGISTER_PRODUCT only, leave the node general enough to extend. Tracked as spec OQ3.
- **A-Q2.** Does partial-success batch need an idempotency key so a retry of a half-landed batch does not double-create? Needs Dario's call; defensible fallback is to dedupe a retry by name within the owner's catalog. Tracked as spec OQ2.

## Source

- Spec: ./specs/001-timonel-flexible-interpretation/spec.md
- Plan: ./specs/001-timonel-flexible-interpretation/plan.md
- Deliberation artifacts: ./specs/001-timonel-flexible-interpretation/.deliberation/
- Panelists who contributed to architecture decisions: Winston, with Amelia, Lattice and Mar'ah on D-004 through D-006.

## Mode

This file was generated fresh on 2026-06-11 by /create-spec.
