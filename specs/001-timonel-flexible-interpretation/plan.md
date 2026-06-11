# Plan: Timonel flexible interpretation and orchestration

## Architecture sketch

One new module and two tightened contracts. The expander is a deterministic data-shape fan-out placed between the router and the resolver; it is the only node that holds the full sibling set and the shared modifier in one scope, which is the precise condition the SKU generator needs before any row is written. See `ARCHITECTURE.md` decisions D-001 through D-006.

```
decomposer -> router -> [ read
                        | expander -> resolver -> write -> read? ]
                        -> final_answer -> (advance sub-input | END)
```

Load-bearing invariants from the panel:

- One vocabulary. Colors and sizes live once in `agents/attributes.py`, imported by both the expander and the resolver's existing `VARIANT_HINT_TOKENS`. (Lattice)
- One writer per fact. The expander owns the desired product set; the resolver owns reconciliation against catalog state; the database owns committed rows. (Lattice, Mar'ah)
- Fail open. The expander never raises into the graph; on any unrecognized phrasing or internal failure it returns the input items unchanged, so no current turn regresses. (Winston)
- Truth from rows. Every summary is built from the rows returned by the database, never from input intent, so the spoken count and the catalog state cannot silently diverge. (Mar'ah)
- Expansion runs before resolver hint logic. `apply_variant_hint` refuses to add a variant when the ref already carries one, which would short-circuit the variants the expander just created; the full graph path must be the verification surface, not the unit alone. (Amelia)

## Sequencing

Two milestone cohorts, each at or under ten children. Milestone M1 is the honest smallest first version: it makes the exact screenshot input provably green. M2 is honest failure, breadth and hardening.

| Milestone | Theme | Covers surfaces | Rough effort |
|-----------|-------|-----------------|--------------|
| M1 | Prove the screenshot: expansion, SKU uniqueness, structured missing-fields, success copy, green golden | S1, S2, S3, S5, S6 | ~5 days |
| M2 | Honest failure and hardening: partial-success batch, overflow and ambiguity guards, idempotency, breadth goldens | S4, S7, S8 | ~4 days |

The single dependency choke is the expander grammar (T-003). Sequence and resource it first; M1 T-005, T-009, T-010 and most of M2 stall behind it.

## Risks

1. **Expansion lands in the wrong layer and stays non-deterministic.** If combinatorics fold into the router LLM prompt, the failing case stops being reproducible in a unit test and drifts on the next prompt edit. Mitigation: the expander is a pure deterministic function with a thin node wrapper; the LLM is a fallback only (D-002), and the screenshot case is a frozen golden (T-002).
2. **Regressing the existing resolver and write_agent suites.** `generate_sku_from_name` and the batch shape are load-bearing for passing tests; token-retention changes can shift existing SKUs. Mitigation: T-007 adds a targeted SKU test and AC10 keeps the current suites green as a gate; the SKU change retains tokens additively rather than restructuring the format.
3. **Silent data divergence between the bot's words and the catalog.** After the batch goes non-atomic, a sub-input that expanded to three products can collapse three outcomes into one success-or-fail flag in `_build_aggregated_summary`. Mitigation: push per-product outcomes up out of `register_products_batch` (T-011) and build the summary from returned rows (T-009, T-012); a golden asserts spoken count equals row count (T-018).
4. **The expander and the router both deciding "is this multiple products".** Two deciders, one question, guaranteed to disagree, with the AMBIGUOUS price-or-stock rule as the casualty. Mitigation: gate the expander to fire only on attribute tokens with no bare-number ambiguity (T-004, AC6).
5. **Expansion blows the per-turn product cap.** Three colors by three sizes is nine products from one phrase; a slightly larger phrase silently truncates a valid set. Mitigation: count before seeding and surface a named overflow (T-014, AC7).

## Dependencies

- No new external services. The cheap LLM (Haiku-class) already wired for decomposer and resolver is the only model dependency, and the expander does not add a mandatory call.
- `database_config` batch helpers exist in two backends (`database_pg.py` Postgres and `database.py` sqlite mirror); both change together for the SKU and partial-success work.
- The fix ships through `/develop --headless` against the GitHub issues this spec opens on `eldaroo/beans-assistant`.

## Cost-shaped considerations

The expander adds no mandatory LLM call on the common path, so per-turn cost is flat for single-product inputs and for deterministic variant lists. The only added model cost is the optional router-prompt hardening (T-017), which is a contract test, not a runtime path change.
