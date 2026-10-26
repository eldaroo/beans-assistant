---
date: 2026-10-26
spec: ./spec.md
architecture: ../../ARCHITECTURE.md
run_id: timonel-tool-use-20261026-010000
---

# Plan 010: Revive native tool-use chat

## Architecture sketch

The spine is unchanged and absolute: the model proposes, the app re-derives the verdict, the only commit path is the non-model `/api/ops/confirm`, the model holds no DB credentials and has no commit tool. This spec swaps the brain (parser -> native tool-use loop on the Nomad box) and reconnects the box to the Next.js write substrate. Decisions D-058 through D-064 in ARCHITECTURE.md.

```
operator turn
      |
      v
  /api/chat (Vercel route)
      |-- append the real message to operator_turns (owner, flowNonce)   [grounding source, D-061]
      |-- mint turnNonce + flowNonce; pin tenant                          [out of band]
      |
      |-- POST beans-ai /run-agent  { utterance, turnNonce, flowNonce, tenant, history }   [D-058, synchronous, bounded budget, D-063]
      |         |
      |         v   (Nomad box: one disposed claude child, --allowedTools mcp__beans__*, built-ins denied)
      |      native tool-use loop
      |         |-- read tool   --> POST Next /api/internal/ops/read/*     --> domain read          [D-059]
      |         |-- write-preview tool --> POST Next /api/internal/ops/stage (x-internal-token, x-beans-tenant, x-beans-turn)
      |         |        --> stageOperation: resolve + ground against operator_turns (NOT tool args, D-061)
      |         |            + computeVerdict + stage pending_ops(op_token)       [op_token stripped from the model, D-062]
      |         v
      |      assistant prose (no op_token ever)
      |
      |-- gateway timeout / error --> fallback parseMessage (the old parser)       [D-058, D-063]
      |
      |-- recover staged ops: verdictPendingForTurn(turnNonce) from pending_ops    [D-062]
      v
  render answer + confirm cards / auto-post (exactly spec 009)
      |-- auto (reversible + grounded + one candidate + within caps + single-turn)  --> client auto-POST /api/ops/confirm + loud Undo
      |-- else                                                                       --> operator-clicked confirm card
      v
  /api/ops/confirm   (session-only, non-model)   [commit, unchanged]
```

Two out-of-band facts cross the box boundary and the model never touches either: the tenant + flow nonce that server-ground the verdict (D-061), and the turn nonce that reads the op_token back from Neon (D-062). That is what makes a tool-use agent safe over the write kernel.

## Sequencing (six cohorts, each at most 10 children)

| Cohort | Delivers | Covers | Depends on |
|--------|----------|--------|------------|
| M1 | Read round-trip: the agent understands a question and reads live data through the gateway + MCP + Next internal read API; parser kept as fallback; the route seam swapped | s-01, s-02 (first read) | none |
| M2 | Full read surface: the rest of the reads + business_status, zero write risk | s-02 | M1 |
| M3 | The service-token write path: `/api/internal/ops/*` auth, grounding keystone, the first reversible write-preview staged and rendered; budget measured | s-03, s-04, s-05, s-09 | M1 |
| M4 | The reversible set end to end: auto-post + loud Undo, the multi-turn-confirm gate | s-05, s-06 | M3 |
| M5 | Irreversible/bulk confirm-only + hardening: per-turn write cap, injection corpus, posture self-check, egress firewall, audit, caps | s-07, s-08 | M4 |
| M6 | Retire the parser to the fallback role and deploy live; the dead-end gone | s-10 | M5 |

Order rationale (Bob). M1 is the cheapest high-visibility win and the proof the whole box boundary works: the agent understands a question and reads live data, zero write risk. M2 fills the read surface. M3 is the keystone cohort: the service-token path (the isolated hard dependency before any write-preview can round-trip), the grounding keystone (operator_turns, not tool args), and the first reversible preview staged and rendered. M4 lights up auto-post + Undo over the reversible set. M5 is the confirm-only tail plus all the security hardening on the new stack. M6 flips the parser to fallback and deploys. Writes never land before the two-phase safety and the grounding keystone are proven.

## Atomic tasks (grouped by cohort; ~31 children)

**M1 — read round-trip (autodev unless noted):**
- T-001: Gateway client in `web/lib/` that POSTs `/run-agent` and returns assistant text + metadata; env `BEANS_AGENT_URL`/`BEANS_AGENT_BEARER`.
- T-002: `/api/internal/ops/read/stock` (and the read route scaffold) delegating to the domain read.
- T-003: Point `beans-mcp.mjs` `BEANS_OPS_URL` at the Next app; confirm `read_stock` round-trips (its test with injected fetch).
- T-004a: Swap the chat route brain: gateway primary, `parseMessage` fallback (the >8h seam, split a).
- T-004b: The response contract: assistant prose + out-of-band nonces threaded into the gateway call (split b).
- T-005: Headless spike: one live read round-trip through the real gateway (human: live run).
- T-006: Synchronous call budget + `maxDuration` + timeout fallback scaffolding (the >8h timeout seam).

**M2 — full read surface (autodev):**
- T-007..T-011: the remaining read endpoints (revenue, profit, sales summary, the eight module snapshots, `business_status` byte-equal to the attention aggregation).

**M3 — service-token write path (autodev unless noted):**
- T-012: `/api/internal/ops/*` service-token auth (constant-time `x-internal-token`), tenant validated against the allowlist (the HARD DEPENDENCY, lands first).
- T-013: `/api/internal/ops/stage` delegating to `stageOperation`; the service token denied at confirm/undo.
- T-014: Grounding keystone: stage grounds against `operator_turns` (`groundingCorpusFor`), never tool args; the invented-numeral test.
- T-015: `flowNonce` threaded from the route into the gateway MCP env and into the stage call.
- T-016: op_token readback via `verdictPendingForTurn(turnNonce)`; render a single reversible preview as a card.
- T-017: Live budget calibration (human: live latency/turn measurement).

**M4 — reversible set + auto-post (autodev unless noted):**
- T-018: Wire the reversible write-preview tools (sale, expense, add-stock) through the internal stage path.
- T-019: Auto-post + loud Undo end to end via the existing client path; the multi-turn-confirm gate (D-064).
- T-020: Per-write and the auto verdict re-proven on the agent path (reuse `verdict.ts`).
- T-021: Live reversible walk at mobile + desktop (human: Kaze/UX walk).

**M5 — irreversible confirm-only + hardening (autodev unless noted):**
- T-022: Wire the confirm-only tools (price, deactivate, cancels, product register/batch) through stage; stay confirm-only.
- T-023: Per-turn write cap (bound auto-post fan-out, AC-T6).
- T-024: Injection corpus on the new stack (no commit, no auto-post from tool output, AC-T5).
- T-025: Boot tool-posture self-check with identical production argv; built-ins denied; one child disposed (AC-T8).
- T-026: Egress firewall config (deny-all except ops host + Anthropic) + the in-code guard (AC-T7).
- T-027: Append-only audit of every tool call + write intent; per-session/global caps (human: security sign-off on the cohort).

**M6 — retire parser + deploy (autodev unless noted):**
- T-028: Parser retained only as fallback; the gateway is primary; the fallback-only test.
- T-029: Deploy the `beans-ai` gateway + the internal API; set `INTERNAL_SERVICE_TOKEN` (human: Dario token mint).
- T-030: Prod verification: a read matches a snapshot, a confirmed sale appears in Ventas, the dead-end is gone (human: prod walk).
- T-031: ARCHITECTURE cross-link + Edut consent sign-off on the revived write model (human: named-human sign-off).

## Risks

1. Serverless timeout. A multi-hop loop (child start + MCP connect + internal round-trip + generation) may exceed the route `maxDuration`. Mitigation: a bounded agent budget under `maxDuration` + `AbortSignal.timeout` + parser fallback (D-063); measure live in M3 (A-Q21).
2. Grounding bypass (the kill risk). If the internal stage path grounds against the model's tool args instead of `operator_turns`, a model-invented numeral auto-posts. Mitigation: ground only against `groundingCorpusFor(owner, flowNonce)` (D-061, AC-T3/AC-T4); the invented-numeral test (T-014).
3. Auto-post fan-out. `numeralIsGrounded` is set-membership, so one grounded operator turn could auto-post many reversible writes. Mitigation: a per-turn write cap (AC-T6, T-023).
4. Service-token blast radius. A leaked `INTERNAL_SERVICE_TOKEN` can stage inert previews (worst case a `pending_ops` DoS). Mitigation: read-plus-propose only, denied at confirm/undo forever, tenant pinned and validated (D-060, AC-T1/AC-T2).
5. Egress. The in-code guard is bypassable by a compromised dependency calling fetch directly; the Nomad network firewall is the load-bearing control (AC-T7).
6. Injection reopened. A tool-use agent is a bigger surface than the parser. Mitigation: injection corpus re-proven on the new stack; commit stays non-model; tool output is never grounded (AC-T5, ports spec 007 AC9).

## Dependencies

- Base branch `claude/008-vercel-migration` (the spec 009 C3 tip merged 2026-10-26).
- Reused unchanged from spec 009: `web/lib/ops/stage.ts`, `web/lib/verdict.ts`, `web/lib/flow-turns.ts` (operator_turns), `web/lib/pending-ops.ts` (`verdictPendingForTurn`), `/api/ops/confirm`, `/api/ops/undo`, the cards/auto-post/Undo in `chat.tsx`, the registry OpDef menu.
- Reused near-verbatim from spec 007 (in-tree): `deploy/beans-ai.nomad.hcl`, the gateway `/run-agent` + tool-posture self-check, `deploy/beans-mcp.mjs` (read + write-preview tools), `deploy/egress-guard.mjs`. The one change to the MCP side is `BEANS_OPS_URL` repointed FastAPI -> Next.
- A deployed `beans-ai` Nomad job with network egress to the Next internal-ops host + Anthropic, and `INTERNAL_SERVICE_TOKEN` shared between the box and the Next app (Dario mints).

## Cost-shaped considerations

The arc reads large but most of the machinery exists: the gateway, the MCP tools, and the entire spec-009 write substrate. The estimable new work is the Next internal endpoints, the service-token auth path, the route seam swap, the grounding wiring, and the security hardening. No new operation types, no new commit path, no new model trust. The one real unknown is live latency of the synchronous loop (A-Q21), measured in M3.
