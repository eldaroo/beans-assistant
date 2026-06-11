# Lattice review — structural integrity

Faculty: cross-domain structural integrity. Where does the load land, and which joint carries more than it was designed for.

## 1. What problem is this actually solving

One owner phrase carries a base noun, a coordinated attribute list, and a shared price. The pipeline has no place that owns the rule "base noun times attribute list equals a concrete product set, each inheriting the shared modifiers." That rule is currently smeared across the decomposer (splits commas), the router (multi-product items), and the resolver (variant hints). The real problem is a missing single owner, not a missing feature.

## 2. Smallest first version

A deterministic expander that runs once, in the decomposer, after the gate and before any LLM. Input one sub-input. Output the cartesian product set with the shared price distributed. Color-only first ("azules y grises a 5"), size second. The router and resolver are not touched in v1. This proves the idea without disturbing the AMBIGUOUS rules.

## 3. Three risks that kill this

- The expander and the router both decide "is this multiple products." Two deciders, one question, guaranteed to disagree.
- The expander multiplies sub-inputs and silently blows the MAX_SUB_INPUTS=10 cap, so a valid phrase gets truncated mid-set.
- A second variant vocabulary is added next to VARIANT_HINT_TOKENS, and the two lists drift.

## 4. Success at 90 days

The four failure phrases pass goldens. No new AMBIGUOUS regression in the eval set. The variant vocabulary lives in exactly one file, imported by both the expander and the resolver. Zero whole-turn hard fails from in-batch SKU collision.

## 5. Atomic tasks

1. Create `attributes.py` holding the single color and size vocabularies. Acceptance: resolver's VARIANT_HINT_TOKENS imports from it, no duplicate literal lists remain (grep proves it).
2. Add `expand_attributes(sub_input) -> list[str]` in the decomposer, deterministic, color-only. Acceptance: "medias azules y grises a 5 dolares" yields two priced sub-inputs.
3. Extend the expander to sizes (talle s/m/l). Acceptance: the multicolor phrase yields three priced sub-inputs.
4. Gate the expander so it only fires when an attribute token is present AND no bare number ambiguity exists. Acceptance: "medias 22, soquetes 15" still routes to AMBIGUOUS, untouched.
5. Count expanded products against MAX_SUB_INPUTS before seeding; surface a named overflow message. Acceptance: a 12-product expansion truncates with a message that names the dropped variants.
6. Dedupe SKUs within a batch against in-flight siblings, retaining size and color tokens. Acceptance: the three size variants get three distinct SKUs in one register_products_batch.
7. Make register_products_batch degrade per-row on residual collision instead of rolling back all. Acceptance: two land, one reports, turn does not hard-fail.
8. Replace indexed missing-field names with "producto X: falta precio." Acceptance: no "ese dato" string reaches the user for an items[] miss.
9. Add the four screenshot phrases to goldens. Acceptance: all four green.

## 6. The one thing only my faculty noticed

Deterministic expansion in the decomposer reaches the catalog while the catalog is empty, which is the onboarding case. But the same phrase replayed later, when "Medias Azules" already exists, must NOT silently re-expand into a duplicate create. The expander produces a desired product SET; whether each member is a create or a no-op is a catalog-state question the expander cannot answer. Put the structural invariant there: the expander owns the desired set, the resolver owns reconciliation against the catalog. One writer per fact. Break that and every new phrasing becomes another special case bolted onto the one before it.
