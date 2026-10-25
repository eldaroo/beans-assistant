---
date: 2026-10-24
spec: ./spec.md
architecture: ../../ARCHITECTURE.md
run_id: timonel-operation-surface-20261024-174517
---

# Plan 009: Timonel full operation surface

## Architecture sketch

The spine is unchanged and absolute: the parser turns an operator turn into a `Proposal`, the app re-derives the verdict, and the only thing that commits is the non-model `POST /api/ops/confirm`. Spec 009 widens three contracts on top of that spine and adds one app-side orchestrator.

```
operator turn(s) in request (role-tagged transcript)
      |
      v
  /api/chat
      |-- kind == "query"  --> read registry (query.ts)  --> rendered answer     [no verdict, no stage, no commit]
      |
      |-- kind == "action" --> for each ProposalStep:
                                 op.resolve(descriptor)  --> server-mints id / candidates   [model never sends ids]
                                   |-- candidateCount > 1 --> disambiguation picker
                                   |-- candidateCount == 1 --> stageOperation
                                                                 |-- computeVerdict (grounded against server-held operator turns of the active flow)
                                                                 |-- auto-post (reversible, grounded) OR confirm card
                                                                 v
                                                             /api/ops/confirm  (non-model, operator-clicked)
```

Guided cost-flows (M7) are an app-side controller that inspects a step's ungrounded required fields and asks the next question; the model only turns the latest operator turn into the next step. No model-held flow state.

The decisions are D-046 through D-052 in ARCHITECTURE.md. D-046 records that the spec-008 propose-only parser is the live brain superseding spec-007's tool-use loop. D-047 the ordered-steps contract. D-048 history-in-request with per-flow grounding. D-049 the QUERY kind. D-050 server-side reference resolution. D-051 the app-orchestrated cost-flow. D-052 the synthesis override: grounding runs against a server-authenticated operator-turn record, not the client transcript.

## Sequencing (cohorts, each a shippable owner-visible increment, each at most 10 children)

| Cohort | Milestones | Delivers | Covers surfaces | Depends on |
|--------|-----------|----------|-----------------|------------|
| C1 | M1 + M4 | The screenshot heals (compound create+act) and the owner can ask questions | s-01, s-02, s-06, s-07, s-16 | none |
| C2 | M2 + M3 | The owner can correct mistakes by chat (cancel, edit price, deactivate) | s-03, s-04, s-05, s-15 | C1 (M3 rides M2; neither needs C1's M4) |
| C3 | M5 + M6 | Multi-turn completion and resume; more operational writes | s-08, s-09, s-10 | none hard; M5 is the keystone C4 needs |
| C4 | M7a + M7b | The cost model becomes feed-able by chatting | s-11, s-12 | C3 (M7 strictly depends on M5) |
| C5 | M8 + M9 | New reads, durable undo, and injection hardening over the whole surface | s-13, s-14, s-17 | all prior (M9 must prove the full surface) |

Order rationale. C1 ships first because it is the cheapest high-visibility value: M1 is the exact screenshot fix and M4 read-dispatch has no dependency on the M2 keystone (reads do not need resolved ids), so pulling M4 forward buys "it answers me" a full cohort early. C2 is the reference-resolution keystone plus its only dependent, corrections. C3 builds the multi-turn keystone M7 needs. C4 is the heaviest and is isolated so it never blocks the cheap wins; it splits M7a (framework plus cost-input, purchase, BOM line, packaging) and M7b (labor, shipping, customs, indirect pool) so each cohort drains honestly. C5 runs injection hardening last so it covers the whole expanded surface.

## Risks

1. Compound atomicity lie. If widening `Proposal` to a list makes a turn commit atomically, a late step's failure strands an earlier irreversible commit, because `/api/ops/confirm` has no cross-step transaction. Mitigation: the step stays the unit of commit (D-047); AC3 names the test that a late-step failure leaves earlier steps intact.
2. Grounding corpus poisoning. If `computeVerdict` grounds numerals against anything other than the operator's own authenticated turns, provenance collapses and injection re-opens on the write path. Mitigation: D-052 server-authenticated operator-turn record; AC10 names the forged-turn test.
3. Model-supplied ids. A hijacked parser that emits `saleId` for a cancel deletes the wrong sale. Mitigation: the model emits descriptors only, the server mints ids (D-050); AC4 names the raw-id-rejection test.
4. M7 scope creep starving the cheap wins. The cost model is the heaviest work; sequenced early or kept as one cohort it starves M1 to M4. Mitigation: M7 is cohort 4, isolated and split M7a/M7b.
5. The auto-post set quietly growing. A new op that lands reversible-and-grounded could auto-post a destructive or money effect. Mitigation: destructive and cost ops carry a permanent registry-level human-review flag (D-052 companion, Edut); AC7 names the test.

## Dependencies

- Base branch `claude/008-vercel-migration` (the new app and ARCHITECTURE.md live here, not origin/main). Spec 009 develops on this line; it does not require the spec-008 M8 cutover first.
- The costing domain's pending-never-zero discipline (`web/lib/domains/costing.ts`) is a prerequisite the guided flow leans on; it exists and is verified.
- M7's indirect-cost pool cross-depends on a production record, so M6's `recordProduction` should land before or with M7b.
- `pending_ops` durable rows (already present) back both durable undo (M8) and the operator-turn grounding record (M5/D-052).

## Cost-shaped considerations

Most of C1 to C3 is wiring over logic and data that already exist, so the attention cost is in the contracts (ordered steps, QUERY union, resolver shape) and the Spanish NL dispatch and formatters, not new engines. C4 (cost model) is the real build. C5 is verification. No new infrastructure, no new credentials, no model tools.
