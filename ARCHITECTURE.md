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

### D-007: The resume path is deterministic code, not a second router call

- **Chosen.** A `resume_gate` node runs before the decomposer and router. When a pending operation matches the reply, it rebuilds the stored entities in code and routes directly into the resolver and write arm.
- **Alternatives considered.** Enrich the router prompt via `pending_entities` so the LLM re-extracts; or re-ask the router constrained to the pending operation.
- **Why this won.** Correctness of a completed financial write must be deterministic. The router is Gemini flash, the named unreliable point, and a wrong completion is a wrong ledger row.
- **Why the alternatives lost.** The first is the current bug: the LLM dropped the product across two turns with context present. The second puts correctness behind a probabilistic call.
- **Implications.** A new entry node sits ahead of the decomposer; the router's "Example 3b" stops being load-bearing for the resume path.
- **Panel source.** Winston, Mary, Amelia.

### D-008: The pending record lives in the per-phone in-process store, not the tenant DB

- **Chosen.** Persist `PendingOperation` alongside the existing `_history_by_key` class state in `ChatService`, keyed by phone, expired by a TTL.
- **Alternatives considered.** A row in the per-tenant SQLite or Postgres DB; a new dedicated store.
- **Why this won.** A pending operation is conversational working state with the history buffer's lifetime and key, and must not survive a restart: a half-finished sale resumed after a deploy is a hazard.
- **Why the alternatives lost.** The tenant DB holds committed facts; an uncommitted intent there invites a reader treating it as real, and restart-survival is the failure we reject. A new store duplicates the buffer's TTL and keying.
- **Implications.** The single-worker assumption is inherited and acceptable; when spec #63 makes history durable, the record rides the same migration.
- **Panel source.** Winston.

### D-009: A new `PendingOperation` type, not the existing `pending_entities` seam

- **Chosen.** A `PendingOperation` carrying `operation_type`, the resolved entities to complete (`product_id`, `quantity`), `missing_fields`, `op_token`, `created_at`. The existing `pending_entities` stays a router-prompt hint, untouched.
- **Alternatives considered.** Extend `pending_entities` to carry resolved ids and drive resume off it.
- **Why this won.** `pending_entities` is a `{name, missing_fields}` prompt hint with no resolved `product_id`, no quantity, no token, and it only populates when `missing_fields` is non-empty (the sale-needs-price branch sets none). Resume needs resolved state.
- **Why the alternatives lost.** One shape spanning an LLM-hint role and a determinism-critical role makes each constrain the other.
- **Implications.** `write_agent`'s sale-price block, returning no pending data today, now emits a `PendingOperation` with `product_id` and `quantity` in hand.
- **Panel source.** Winston, Amelia.

### D-010: Completion is idempotent via an op_token recorded at commit

- **Chosen.** Each `PendingOperation` is stamped with an `op_token` at creation. Resume clears the record before commit; the committed sale records the token; a second resume of the same token is refused.
- **Alternatives considered.** Trust the single-worker model and skip the token; dedupe by a (product, quantity, minute) heuristic.
- **Why this won.** Never double-record a sale is the hard constraint. A retried turn, double-tapped send, or graph retry must commit once; only a token survives all.
- **Why the alternatives lost.** In-process storage does not stop a retried turn resuming a still-present record. A heuristic can suppress a legitimately repeated sale.
- **Implications.** Resume clears-then-commits: a crash mid-commit loses the resume rather than risking a double.
- **Panel source.** Winston, Mar'ah.

### D-011: The pending record expires by TTL and is cleared on cancel or change of mind

- **Chosen.** A record older than the configured TTL never resumes. A cancel, or any reply the gate cannot match to the missing field, clears it (or leaves it to re-ask) and falls through to the cold path.
- **Alternatives considered.** Keep the record until explicitly resumed; resume on any numeric reply.
- **Why this won.** Handling cancel and change-of-mind mid-detour is in scope. A pause is not a lock; a stale resume is a wrong ledger row, so expiry and cancel-clears default safe.
- **Why the alternatives lost.** An indefinitely held record resumes a phantom an hour later; resuming on any number guesses, which the constraint forbids.
- **Implications.** The match fills only when the reply unambiguously is the missing field; otherwise the gate re-asks or clears.
- **Panel source.** Winston, Mar'ah, Edut.

### D-012: Resume serves only fully-resolved paused operations in v1

- **Chosen.** Resume fires only when the paused operation holds every entity except the one missing field. Operations needing fresh disambiguation cold-classify.
- **Alternatives considered.** A general resume that re-resolves arbitrary missing entities across turns.
- **Why this won.** A resolved-except-one-field pause is a closed, testable transition. Re-resolving an arbitrary entity reintroduces the LLM, which D-007 forbids.
- **Why the alternatives lost.** A general re-resolver is a larger surface that puts the unreliable path back on the money line.
- **Implications.** v1 covers sale-needs-price and (M2) one more single-missing-field pause; broader resume is a later spec.
- **Panel source.** Winston.

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
- **A-Q3.** Pending-operation idempotency: an `op_token` column on the `sales` row, or an in-process committed-token set keyed by phone? Fallback: in-process set for v1 (single worker), a column when spec #63 lands durability. Tracked as spec 002 Q1. (D-010)
- **A-Q4.** Should resume serve ADD_STOCK paused on quantity in v1? Fallback: sale-needs-price only in M1, ADD_STOCK in M2. Tracked as spec 002 Q2. (D-012)

## Source

- Spec: ./specs/001-timonel-flexible-interpretation/spec.md
- Plan: ./specs/001-timonel-flexible-interpretation/plan.md
- Deliberation artifacts: ./specs/001-timonel-flexible-interpretation/.deliberation/
- Panelists who contributed to architecture decisions: Winston, with Amelia, Lattice and Mar'ah on D-004 through D-006.
- D-007 through D-012 (pending-operation completion): ./specs/002-timonel-pending-operations/spec.md and ./specs/002-timonel-pending-operations/plan.md. Panel: Winston (author), with Mary, Amelia, Bob, Edut, Mar'ah.

## Mode

This file was generated fresh on 2026-06-11 by /create-spec. Updated 2026-06-14 by /create-spec (spec 002 timonel-pending-operations) appending D-007 through D-012; D-001 through D-006 untouched.
