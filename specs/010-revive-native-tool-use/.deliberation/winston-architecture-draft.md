---
name: timonel-architecture-delta
spec: 010-revive-native-tool-use
mode: update
author: Winston (BuildOS Architect, architecture-author role)
last_ordinal_before: D-057
new_decisions: D-058..D-064
---

# Architecture delta — Spec 010: revive spec-007 native tool-use on the Vercel/Neon stack

Mode: UPDATE. Scope: only the decisions that put the native tool-use brain back in
front of spec 009's write spine, re-homed to the new stack. Everything in D-001..D-057
not named here is untouched. New decisions continue from D-057, so they begin at D-058.
This pivot supersedes the D-053..D-056 slot-filling controller draft (see D-064); the
spine stays absolute — the model never commits, writes are two-phase, the verdict is
server-computed.

## The shape (what moves, what stays)

The gateway box already carries the whole loop: `/run-agent` (a disposed child per
request, `--max-turns`, token rotation), the boot tool-posture self-check
(`tool-posture.mjs`, D-035), the egress guard, and the beans MCP server with read tools
and write-preview tools that call `/internal/ops/*` with `x-internal-token`,
`x-beans-tenant`, and `x-beans-turn` out of band. What is dead is the *other end of
that wire*: the MCP tools point at a FastAPI internal API that spec 008 deleted. The
spec 009 write substrate — `stageOperation`, `computeVerdict`, `operator_turns`
(`flow-turns.ts`), `pending_ops` (`verdictPendingForTurn`), `/api/ops/confirm`,
`/api/ops/undo`, the cards/auto-post/Undo in `chat.tsx` — is the correct substrate and
is reused, not rebuilt. This spec reconnects the box to Next and swaps the chat seam.

## Decision log

### D-058: The chat brain is the native tool-use loop on `beans-ai`; the propose-only parser becomes the fallback (supersedes D-046)

- **Chosen.** `web/app/api/chat/route.ts` calls the gateway `/run-agent` (passing the
  operator utterance, a server-minted `turnNonce` and `flowNonce` out of band, and a
  bounded history) instead of `parseMessage`. The model understands the whole turn and
  drives the beans MCP tools. `parseMessage` (the spec-008/009 parser) is retained **only
  as the degrade path** when the gateway errors or times out.
- **Supersedes D-046,** which made the propose-only parser the live brain after the 008
  cutover. The parser was never the right brain; it was the serverless-safe stopgap. It
  is now the fallback, not the brain.
- **Why.** One reasoner over a fixed tool set removes the parser's dead-end on anything
  outside N ops (Dario, 2026-10-26). Keeping the parser as fallback means a gateway
  outage degrades to "dumb but working," never to "down."
- **Implications.** The swap seam is one call in the route. The envelope the route
  returns (`proposal` / `compound` / `needs` / `answer`) is unchanged, so `chat.tsx`
  renders identically.
- **Panel source.** Winston; Dario (binding re-home choice, native loop on the box).

### D-059: The MCP internal operation API is re-homed from the dead FastAPI to the Next.js app (re-homes D-036)

- **Chosen.** The beans MCP tools keep calling `/internal/ops/*`, but `BEANS_OPS_URL`
  now points at the Next app. **Read tools** (`read_stock`, `read_revenue`, …,
  `business_status`) call the existing domain reads (`lib/domains/*`,
  `attention_service` equivalent) behind these endpoints. **Write-preview tools**
  (`register_sale`, …) call endpoints that delegate to `stageOperation` — which already
  re-derives resolution, grounded amounts, the verdict, and stages an `op_token`.
- **Why.** The app that owns the DB owns re-validation and the verdict. `stageOperation`
  is exactly the FastAPI `preview_*` contract's replacement; `callPreview` already strips
  `op_token` before returning to the model, so the tool shapes need no change.
- **Implications.** `beans-mcp.mjs` is reused near-verbatim; the work is the Next
  endpoints behind the same paths and the `BEANS_OPS_URL` repoint. D-036's "tools hold no
  DB credentials, call an authenticated internal API" is preserved; only the API's host
  moves FastAPI → Next.
- **Panel source.** Winston, grounding Amelia's "reuse the endpoint contracts."

### D-060: Internal service-token auth is a dedicated `/api/internal/ops/*` route family; the session routes are untouched; tenant is pinned and validated out of band

- **Chosen.** A new route family authenticates with `INTERNAL_SERVICE_TOKEN`
  (`x-internal-token`, constant-time compared), **not** `auth()`. It reads the tenant from
  `x-beans-tenant` and validates it against the single-business allowlist — the tenant is
  never trusted as arbitrary and never a model-settable arg (D-037). The session routes
  (`/api/chat`, `/api/ops/stage`, `/api/ops/confirm`) keep `auth()`; the commit path stays
  session-only, so the Nomad box can stage but can never commit.
- **Why.** The box has no user session; it needs a service identity. A separate route tree
  keeps the service path from ever widening the session path, and keeps the token's blast
  radius to read + stage.
- **Implications.** Two auth substrates, cleanly split: session (owner UI, commit) and
  service token (box, read + preview). A-Q17 is resolved: shared `INTERNAL_SERVICE_TOKEN`
  with tenant pinned and Next re-validation for now; per-request minting only if the
  callback path widens.
- **Panel source.** Winston, grounding Tamir on the write boundary.

### D-061: The operator's real utterance reaches `computeVerdict` only via the server-authenticated `operator_turns` record, never via model tool args (re-affirms D-041/D-052)

- **Chosen.** Before calling the gateway, the route appends the real inbound message to
  `operator_turns` keyed by `(owner, flowNonce)` and injects `flowNonce`/`turnNonce`/tenant
  into the gateway's per-request MCP env out of band. The internal preview endpoint, on a
  tool call, builds `utterance` and `groundingCorpus` **from that server record**
  (`groundingCorpusFor(owner, flowNonce)`), not from anything the model passed, and hands
  them to `stageOperation`. The model's tool-supplied numeral lives only in `args` and is
  *grounded against* the server corpus.
- **Why.** This is the keystone the re-home must not lose. In the tool-use loop the model
  proposes write args; a tool-sourced or model-invented numeral must not auto-post. Because
  grounding reads the operator's own recorded words (D-052) and not the args, an invented
  numeral fails grounding → `auto:false` → confirm card. Provenance laundering (D-041) stays
  closed across the box boundary.
- **Implications.** The MCP preview tool threads a `flowNonce` header alongside the existing
  `x-beans-turn`. The bare-confirmation guard still reads the *current* turn, so "dale"
  alone never auto-posts.
- **Panel source.** Winston, sharpened by Tamir (grounding is a check outside the model).

### D-062: The `op_token` never crosses the gateway or the model; the route reads staged ops back from `pending_ops` by the turn nonce it minted

- **Chosen.** `callPreview` already strips `op_token` before returning to the model, and
  the gateway returns only assistant prose. So after `/run-agent` returns, the route obtains
  commitable handles by reading `pending_ops` with `verdictPendingForTurn(turnNonce)` — the
  nonce it minted and injected out of band — then renders cards / auto-post exactly as spec
  009. Commit stays `/api/ops/confirm`.
- **Why.** No path may hand the model (or a hijacked model) something that could commit. The
  token lives in Neon, keyed by the server's own nonce; the gateway is a prose channel only.
- **Implications.** `verdictPendingForTurn` already exists (D-047 substrate). The route loops
  it to render an ordered multi-step turn. A write with no staged op means the model only
  talked — render the prose.
- **Panel source.** Winston (keystone).

### D-063: The route → gateway call is synchronous with a bounded agent budget under `maxDuration`; timeout falls back to the parser

- **Chosen.** The chat route awaits `/run-agent` synchronously. The agent budget
  (`BEANS_AGENT_MAX_TURNS`, `BEANS_AGENT_TIMEOUT_MS`) is tightened to fit under the route's
  `maxDuration` (Pro/fluid), and the fetch carries an `AbortSignal.timeout` below it. On
  timeout or a `model-error`, the route falls back to `parseMessage` (D-058), so a slow or
  dead box degrades to the parser rather than a 504.
- **Why.** A multi-hop loop (child start + MCP connect + internal round-trip + generation)
  is the real latency tension (context packet). Synchronous-with-fallback is the smallest
  design that ships; an async poll/stream is the escalation only if the budget cannot fit.
- **Implications.** M3 measures live and sets the budget. A-Q19 resolved: cap `--max-turns`
  low, measure, add a tool-call counter only if a turn loops.
- **Panel source.** Winston, with Amelia on the live budget.

### D-064: Model-native multi-turn understanding supersedes the slot-filling controller (D-053..D-056); D-057's multi-turn-confirm consent gate is retained

- **Chosen.** The app-side slot-filling state machine (D-053 `requiredSlots`, D-054 partial
  op, D-055 controller, D-056 completion handoff) is **not built**: the native loop owns
  multi-turn understanding ("a que precio?" is the model asking, then the operator answering,
  grounded per-turn via D-061). D-057's rule is **retained**: an op whose load-bearing
  grounding spans more than the current turn never auto-posts — `computeVerdict` forces
  `auto:false` so the operator assents to the assembled whole on a final card.
- **Why.** The slot controller existed to give a dumb parser multi-turn memory; a reasoner
  needs none. But the *consent* reason for D-057 (the owner never saw "40 stanleys at 32"
  assembled) is independent of which brain assembles it, so it survives.
- **Implications.** D-053..D-056 are marked superseded-by-D-064 in the log; their consent
  invariant lives on as the multi-turn verdict gate.
- **Panel source.** Quinn synthesis of the Winston (native loop) and Edut/Tamir (consent)
  lenses.

## Carry-forward ledger (spec-007 decisions on the new stack)

| Decision | Status on Vercel/Neon |
|----------|----------------------|
| D-034 native loop | **Revived**, chat seam now the Next route, not FastAPI `ChatService` |
| D-035 posture / denylist / self-check | **Unchanged** — code already on the box |
| D-036 tools hold no DB creds, call internal API | **Re-homed** (D-059): internal API FastAPI → Next |
| D-037 tenant out of band, never model-set | **Unchanged** (reinforced by D-060/D-061) |
| D-038 two-phase, commit non-model | **Unchanged** — reuses `stage`/`/api/ops/confirm` |
| D-039 phone from session | **Re-homed** — route resolves owner, pins it into the gateway call |
| D-040..D-044 verdict doctrine | **Unchanged** — already live in `verdict.ts`/`stage.ts` |
| D-046 parser-as-brain | **Superseded by D-058** — parser is now the fallback |
| D-052 operator_turns grounding | **Unchanged** — the keystone for D-061 |
| D-053..D-056 slot controller | **Superseded by D-064** |
| D-057 multi-turn confirm gate | **Retained** (D-064) |

## Open architectural questions (spec 010)

- **A-Q21.** Does the tightened agent budget fit under the route `maxDuration` at live
  latency, or must the call go async (poll/stream)? Fallback: synchronous + parser fallback;
  measure in M3. (D-063)
- **A-Q22.** The `flowNonce` the box must thread for grounding: a new MCP preview header, or
  folded into `x-beans-turn`? Fallback: a distinct header, since turn and flow have different
  lifetimes. (D-061)
- **A-Q23.** When the gateway loop reads a tool result then stages a write in the same turn,
  is the per-session tool-call cap tight enough to bound a runaway loop? Fallback: measure,
  add a tool-call counter if a turn loops. (D-063, D-035)
