# ARCHITECTURE.md — spec 009 addendum (ARCHITECTURE-AUTHOR, mode = UPDATE)

Winston, 2026-10-24. New decisions start at **D-046**. Emits only what spec 009 changes.

> **Read before building on D-034..D-045.** Those describe spec 007's native tool-use loop (`mcp__beans__*`, `/run-agent`, boot posture check). Spec 008 **retired that loop** at the Vercel+Neon cutover. The live brain is the stateless **propose-only parser** (`web/lib/parse/*`) → app-recomputed verdict (`verdict.ts`) → two-phase stage (`pending-ops.ts`, `ops/stage.ts`) → non-model commit (`/api/ops/confirm`). Spec 009 extends *that*. D-046 records the cutover; D-047..D-051 resolve the load-bearing choices.

### D-046: The spec-008 propose-only parser is the live brain; spec-007's tool-use premise is superseded, its verdict doctrine kept

- **Chosen.** Record that D-034..D-039 (tools on the model, internal-ops callback, boot posture check) no longer describe the system. The parser holds no DB credential, tools disabled, one turn, bearer-gated, fails closed. **Kept, ported verbatim:** D-040–D-044's verdict doctrine now lives in `verdict.ts`/`stage.ts` — reversible set, server-computed provenance, determinism, confirm-only.
- **Alternatives.** (a) Leave the doc describing the retired loop. (b) Re-add model tools for "power."
- **Why this won.** The doc must match the code a future author greps. "Power" is a UX feeling from app orchestration (Dario, 2026-10-24), not model capability.
- **Why alternatives lost.** (a) A doc that lies about the write path is worse than none. (b) Tools reopen the injection-to-commit surface spec 005/007 closed, at the latency 008 rejected.
- **Panel source.** Winston; Dario (locked).

### D-047: The `Proposal` contract widens to an ordered LIST of steps; the step stays the unit of commit

- **Chosen.** The parser response becomes an ordered `steps: ProposalStep[]`, not a single op. Every step is resolved, verdicted, staged, and confirmed **independently** — one step, one `op_token`, one verdict, one `/confirm`. The list is the turn's intent; the step is the commit. No cross-step transaction.
- **Alternatives.** (a) Keep `Proposal` singular; chain app-side. (b) Widen to a list *and* commit it atomically.
- **Why this won.** `pending-ops.ts` already carries this substrate — `turnNonce` correlates many staged ops to one turn and `verdictPendingForTurn` returns an ordered list. Widening the contract *finishes* a half-built mechanism, keeping the proven per-op verdict intact. M1 ships app-side first (zero parser change) as proof; the list is the durable contract M7 needs.
- **Why alternatives lost.** (a) App-side chaining can't express "one ordered intent" without hardcoding each compound; won't generalize to M7. (b) Atomic-commit is a lie — `/confirm` has no multi-row transaction, so a late failure strands an earlier irreversible commit.
- **Implications.** `types.ts` gains the list; `fallback.ts` wraps its result in a one-element list; the route loops `stageOperation` per step under one `turnNonce`; step N+1 may reference step N's committed result (D-050); `chat.tsx` renders an ordered multi-step card.
- **Panel source.** Winston.

### D-048: Multi-turn context travels in the request; grounding is bounded to the operator's own turns in the active flow

- **Chosen.** History lives in the **request** (`chat.tsx` already holds the transcript). `/api/chat` accepts a bounded, role-tagged transcript; the parser stays stateless per call. Provenance widens from per-turn to **per-flow**: `computeVerdict` grounds numerals against the union of the **operator's own** turns in the active flow — never assistant replies, never other-business data. The flow resets on commit or cancel.
- **Alternatives.** (a) A server-side session/flow table (dropped specs 001/002). (b) Keep provenance per-turn.
- **Why this won.** History-in-request keeps parser and server stateless and serverless-friendly, reintroducing none of the flow-row weight 008 dropped. Per-flow grounding lets "vendí 40 stanleys" / "a qué precio?" / "32" complete while numerals still trace to the operator.
- **Why alternatives lost.** (a) A server flow store is the stateful weight the rebuild removed. (b) Per-turn grounding fails every multi-turn completion, forcing a confirm card on the common case.
- **Implications.** Transcript role-tagged; assistant turns **non-grounding** by construction (the poisoning risk); window bounded to the active flow. The grounding check stays defense against the *model*, as in D-041.
- **Panel source.** Winston; restores specs 001/002 atop the spine.

### D-049: QUERY is a distinct read-only kind, dispatched before staging, off the write path by construction

- **Chosen.** `Proposal` becomes a discriminated union; a `QUERY` step names a read and carries no verdict, `op_token`, or `pending_ops` row. The route branches on `kind === "query"` **before** `stageOperation`, dispatches to a **separate read registry** (no `commit`/`undo`/`irreversible` field), returns a rendered answer.
- **Alternatives.** (a) A QUERY op in `OPS` with a no-op commit. (b) Keep reads on `handleScenario` only.
- **Why this won.** Separation by *type* plus a registry with no commit surface structurally guarantees a read can never acquire a write path. The ~15 reads already exist as domain fns behind GET routes; this only dispatches them.
- **Why alternatives lost.** (a) A no-op-commit op still flows through verdict/stage/confirm — one edit from a committing "query." (b) `handleScenario` answers one of ~16.
- **Implications.** `computeVerdict` never runs; nothing stages. Reads are tenant-scoped by auth as the GET routes are; M9 proves no leak of cross-business rows.
- **Panel source.** Winston; keystone 2.

### D-050: Reference resolution is a server-side read inside `op.resolve()`; the model emits descriptors, never ids

- **Chosen.** The parser emits a reference **descriptor** ("la última venta", "la venta de Juan"), never a numeric id. New resolvers (`resolveSale/Expense/StockMovement`) mirror `resolveActiveProduct`: descriptor → `{candidateCount, id|null, candidates}`, inside the op's `resolve()`. 0 → clean error; **>1 → the M2 picker**, each option carrying the server-resolved id; 1 → id in `stagedArgs`. In a compound (D-047), step N+1 resolves against step N's result.
- **Alternatives.** (a) Parser supplies the id. (b) Resolve in the route, outside the op.
- **Why this won.** D-042's determinism check generalized from products to every correctable entity, reusing the live mechanism. The id is always server-derived, so a hijacked model cannot target `saleId: 999` — D-041 provenance-laundering re-aimed at the cancel path.
- **Why alternatives lost.** (a) A model-supplied id is injectable and unchecked — the destructive footgun. (b) Resolving in the route bypasses the `candidateCount` gate that routes ambiguity to a card.
- **Implications.** Cancels/edits stop taking raw ids. The picker is a QUERY-shaped response (D-049); selecting re-enters staging with its server-resolved id.
- **Panel source.** Winston; keystone 1.

### D-051: M7 guided cost-flows stay propose-only via an app-orchestrated question loop; the model never holds flow state

- **Chosen.** Each cost write (recordBomLine, recordPackagingCost, …) is one irreversible step → always a confirm card. The flow is orchestrated **app-side**: a controller inspects the ungrounded required fields and asks the next question; answers accumulate in the request (D-048); interdependencies resolve by server-side reads (D-050). The model only turns the latest operator turn into the next `ProposalStep`.
- **Alternatives.** (a) One compound proposal for the whole cost model. (b) Give the model a flow scratchpad/memory.
- **Why this won.** Per-step propose-only keeps every cost write grounded and confirmable field-by-field; the owner enters the model by chatting (Dario, 2026-10-24), with no atomic blob that strands on one bad field.
- **Why alternatives lost.** (a) A whole-model compound is ungroundable and non-atomic (D-047). (b) Model-held flow state is injection surface the spine forbids.
- **Implications.** The controller is app code reading `missing_fields`; cost ops enter `OPS` as irreversible, leaning on D-048 and D-050. Heaviest milestone, no new spine.
- **Panel source.** Winston; Dario's cost-entry call.

### D-052: Numeral grounding runs against a server-authenticated operator-turn record, not the client transcript (synthesis override, refines D-048)

- **Chosen.** D-048 keeps history in the request for context and resume, but grounding does NOT trust the client-supplied transcript. The server keeps a lightweight, nonce-bound, append-only record of the operator's own turns for the active flow (operator utterances only, cleared on commit or cancel, not a full conversation store). `computeVerdict` grounds numerals against THAT record. The client transcript carries display context; it never feeds the grounding corpus.
- **Alternatives.** (a) D-048 as written: ground against the request-carried transcript, trusting its operator/assistant role tags. (b) A full server-side conversation store (the dropped specs 001/002 weight).
- **Why this won.** Tamir (threat) and Amelia (dev) converged independently: a client-supplied transcript lets a forged "operator" turn carrying a numeral launder an ungrounded amount onto the auto-post path, which D-048's assistant-turn exclusion does not defend against, since the attacker controls which turns are tagged operator. Edut's consent lens agrees: an auto-post must trace to what the owner actually said, server-verified. Grounding against a server-held record closes that without the full session table 008 removed.
- **Why alternatives lost.** (a) Trusting the client's role tags is the exact provenance-laundering hole. (b) A full conversation store is the stateful weight the rebuild dropped and is more than grounding needs.
- **Implications.** A small append-only operator-turn store (pending_ops-adjacent, keyed by flow nonce) backs grounding; it is operator-turns-only and flow-scoped, so it is far lighter than a session table. This is server state, which the 008 rebuild tried to avoid, and is named as spec Open Question 1 for Dario. Destructive and cost ops additionally carry a permanent registry-level `requiresHumanReview` flag (Edut) so no grounding change can promote them to auto-post.
- **Panel source.** Quinn synthesis, resolving the Winston (D-048) vs Tamir/Amelia/Edut disagreement toward the security and consent lens (wal-ledger specialist-override precedent).
