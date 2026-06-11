# Bob (Scrum Master) review — Timonel flexible interpretation

## 1. What problem is this actually solving?

An owner typed one ordinary Spanish sentence and got two failures: a missing-data ask that named nothing, and a hard rollback on a SKU collision. The real problem is that Timonel cannot turn "base noun plus a variant list plus a shared price" into the set of concrete products the owner meant, and when it stumbles it tells the owner nothing useful. We are making interpretation distribute shared modifiers across a coordinated list, and making failure legible.

## 2. What is the smallest first version that proves the idea?

Milestone A below. It makes the exact screenshot input provably green: the two sentences expand to two and three products, all five land, and the summary names each. That is the whole thesis on the one input that failed. Everything after A is breadth.

## 3. What 3 risks would kill this if ignored?

- Over-reaching into the LLM when the grammar is regular. Color and size lists are deterministic. Pushing them into the decomposer LLM adds cost and flakiness and makes the failing case non-reproducible in a unit test.
- Fixing the screenshot without a frozen golden, so the next prompt edit silently regresses it.
- Treating attribute expansion, SKU dedupe, and message copy as one blob. They have different verification shapes and must not share a task.

## 4. What does success look like at 90 days?

The screenshot input and a dozen sibling phrasings are green goldens in CI. Batch creates never hard-fail a whole turn on a SKU collision. Missing-field messages always name the product and the field. No new mandatory LLM call sits on the single-intent path.

## 5. Atomic tasks (dependency-ordered, milestone cohorts <= 10)

Legend: [D] pure deterministic, verifiable by named unit test. [L] touches an LLM prompt, verified by golden plus an offline contract test on the parsed shape.

### Milestone A — prove the screenshot (smallest honest first version)

- A1 [D] Add failing golden for the screenshot input. Acc: `tests/eval/test_attribute_expansion.py::test_screenshot_input` exists and fails red. Est 2h. Dep: none.
- A2 [D] Batch-local SKU dedupe in `register_products_batch` (`database_config.py`): dedupe against in-flight siblings, suffix on collision. Acc: unit test feeds three identical base SKUs, three distinct rows land. Est 4h. Dep: none.
- A3 [D] Retain discriminating tokens in `generate_sku_from_name` (resolver.py ~897): keep size and color tokens, stop dropping single-letter size tokens (s/m/l). Acc: unit test, three sizes yield three distinct base SKUs. Est 4h. Dep: none.
- A4 [D] Deterministic attribute-expander module: base noun + color/size list + trailing shared price -> items list, each inheriting price. Acc: `test_expand_variants` covers "medias azules y grises a 5 dolares" -> 2 items and "talle s, m y l a 10 dolares" -> 3 items. Est 8h. Dep: none. (Watch: this is the load-bearing one; keep the grammar in its own pure function.)
- A5 [D] Wire expander output into router `items` shape before write_agent. Acc: integration test, router state carries 5 populated items for the screenshot. Est 6h. Dep: A4.
- A6 [D] Per-item missing-field naming: replace `items[i].field` with "Producto X: falta el precio". Acc: unit test on `_compute_per_sub_input_answer` asserts no "ese dato" for indexed names. Est 4h. Dep: none.
- A7 [D] Turn the A1 golden green end to end. Acc: A1 passes, five products created, summary names each. Est 3h. Dep: A2, A3, A5, A6.

### Milestone B — breadth and hardening

- B1 [D] Graceful in-batch collision recovery: on residual collision, create what can, report the rest, never roll back all. Acc: `test_partial_batch_recovery`. Est 6h. Dep: A2.
- B2 [L] Router prompt examples for variant phrasing, with offline contract test on parsed `items`. Acc: golden suite over 8 phrasings. Est 6h. Dep: A5.
- B3 [D] Author live `ARCHITECTURE.md` documenting the expander seam. Acc: file exists, references the new module. Est 3h. Dep: A7.
- B4 [D] Sibling-phrasing golden pack (10 inputs). Acc: all green in CI. Est 6h. Dep: A7, B1.

Flagged as secretly two tasks: the original "attribute expansion" idea hides A4 (the grammar) and A5 (the wiring). I split them. A2 and A3 also look like one SKU fix but are distinct: dedupe scope versus token retention.

Honest smallest first version: Milestone A. Ship it alone and the failing screenshot is green.

## 6. The one thing only my faculty would have noticed

A4 the expander grammar is the only task on the critical path of every other green; sequence it first and resource it as a full day, not a half. If it slips, A5, A7, B1, B2, B4 all stall. It is the single dependency choke and the one to protect.
