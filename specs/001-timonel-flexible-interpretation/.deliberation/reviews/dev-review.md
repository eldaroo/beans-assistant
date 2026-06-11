# Dev review — Amelia (Senior Developer)

Grounded in the real files under `clients/eldaroo/beans-assistant/`.

## 1. What problem is this actually solving

One real sentence ("medias azules y grises a 5 dolares, y medias multicolor talle s, m y l a 10") must become five products at the right prices, or fail with a message that names what is missing. Today it produces zero products and "ese dato, ese dato". The work is interpretation (expand variants) plus honest failure (name the gap, never roll back the whole turn).

## 2. Smallest first version that proves the idea

Deterministic attribute expansion in the decomposer for the regular grammar `base-noun + [color|size list] + shared price`, feeding the existing router `items[]` shape, plus an in-batch SKU dedup. No new LLM call. That alone turns the screenshot from two failures into five created products.

## 3. Three risks that would kill this

- Expansion in the wrong layer. If it lands in the router LLM prompt it stays non-deterministic and re-breaks. It belongs in `decomposer.py` as code.
- Regressing `test_resolver.py` (25 tests) and `test_write_agent.py`. `generate_sku_from_name` and batch shape are load-bearing for passing tests; changing token retention can shift existing SKUs.
- The `_advance_sub_input` reset list. Expansion that smuggles per-variant data through `normalized_entities` across sub-inputs will be silently wiped by `TURN_SCOPED_FIELDS` (decomposer.py:232).

## 4. Success at 90 days

The screenshot input creates five products in one turn. Zero "ese dato" in logs. Batch SKU collisions are zero. `tests/eval/decomposer.json` and `tests/eval/resolver/golden.json` carry variant-expansion goldens that stay green on CI.

## 5. Atomic tasks

1. **Variant-expansion grammar in decomposer.** Add `expand_attributes(sub_input)` producing concrete name + shared price per variant. Accept `medias azules y grises a 5` -> 2, `medias multicolor talle s, m y l a 10` -> 3. Acceptance: `tests/unit/test_decomposer_expansion.py` passes: "medias azules y grises a 5" -> 2 items both unit_price 5.
2. **Route expanded set into router `items[]`.** Ensure expanded products reach `REGISTER_PRODUCT` items shape, not single-name. Acceptance: `tests/integration/test_decomposer_graph.py` asserts entities `items` length 2 for the azules/grises case.
3. **In-batch SKU dedup.** In `register_products_batch` (database_pg.py:360) AND `database.py` sqlite mirror, dedup `sku` against in-flight siblings before insert, suffixing `-2`, `-3`. Acceptance: `tests/unit/test_database.py` passes: three "Medias Multicolor Talle S/M/L" yield three distinct SKUs, all rows land.
4. **Retain discriminating tokens in SKU.** In `generate_sku_from_name` (resolver.py:947-963) stop dropping single-letter size tokens; keep size/color descriptors. Acceptance: `test_resolver.py::test_sku_keeps_size_token` passes: "Medias Multicolor Talle S" SKU != "Medias Multicolor Talle M".
5. **Translate indexed missing-field names.** `validate_required_fields` (resolver.py:1027-1031) emits `items[0].name`; map to "el nombre del primer producto" naming the item. Acceptance: `test_write_agent.py::test_indexed_missing_translates` asserts no "ese dato" for `items[1].name`.
6. **Single translation table.** Extract the duplicated dict from write_agent.py:104-117 and graph.py:380-394 into `agents/field_labels.py`; both import it. Acceptance: `grep -c field_translations agents/` shows one definition; full suite green.
7. **Graceful batch collision.** When dedup still collides, create the survivors and report the offender by name, not whole-turn fail. Acceptance: `test_write_agent.py::test_partial_batch_reports_offender` passes.
8. **Eval goldens.** Add the two screenshot cases to `tests/eval/decomposer.json` and resolver golden. Acceptance: `tests/eval/decomposer/run_eval.py` exits 0 with the new cases.

## 6. The one thing only my faculty noticed

`apply_variant_hint` (resolver.py:397-430) refuses to add a second variant when a `product_ref` "already has ANY variant". After expansion, "Medias Azules" already carries a color, so the hint guard short-circuits exactly the variants you just created. The expansion task must run BEFORE resolver hint logic, or task 1 will pass in isolation and silently regress through the resolver. Wire and test the full graph path, not the unit alone.
