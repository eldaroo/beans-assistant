# Amelia — Developer review (spec 010, Timonel native tool-use re-home)

Lens: the concrete wiring of the re-home. All paths cite the beans-spec010 worktree.

## 1. What problem is this actually solving?
The propose-only parser (`web/lib/parse/client.ts` -> `beans-parse`) collapses every message onto one of N fixed ops and dead-ends on everything else — "tonto". Spec 007's native tool-use loop already exists in the tree (`deploy/beans-ai.nomad.hcl` carries a live `/run-agent`, `runAgentTurn`, `agentFlags`, the posture/egress self-checks; `deploy/beans-mcp.mjs` carries every read + write-preview tool). The problem is purely wiring: the MCP tools call a dead FastAPI, and the Vercel route still calls the parser. We re-point, we do not rebuild.

## 2. The smallest proof on the new stack
Two round-trips, nothing else.

**READ:** chat route POSTs `{prompt, system, turn_nonce}` to the gateway `/run-agent` -> `runAgentTurn` leases a `claude` child -> child calls `mcp__beans__read_stock` -> `callRead` (beans-mcp.mjs) POSTs `/api/internal/ops/read_stock` on Next with `x-internal-token` + `x-beans-tenant` -> a NEW thin internal route calls `lib/domains/*` -> `{ok,stock}` back up -> gateway returns `{ok,text}` -> route renders `kind:"answer"`. One new internal route + the two env vars (`BEANS_OPS_URL`, `INTERNAL_SERVICE_TOKEN`, already in the HCL template) proves the whole spine.

**WRITE-PREVIEW:** "vendi 2 medias a 300" -> child calls `mcp__beans__register_sale` -> `callPreview` POSTs `/api/ops/stage` (second auth branch) -> `stageOperation` re-derives resolution + verdict + stages an op_token. The route then renders the 009 confirm card / auto-post unchanged. This proves grounding + verdict + card survive the re-home.

## 5. Atomic tasks (naming real files)
1. **Internal read routes.** Add `web/app/api/internal/ops/[read]/route.ts` (or one file per read) returning `{ok,<key>}` shapes `callRead` expects (`read_stock`->`stock`, `read_revenue`->`revenue`, `read_sales_summary`->`sales_summary`, `read_module`->`module`, `business_status`->`attention`). Thin wrappers over `lib/domains/*` + `lib/ops/query`.
2. **Service-token auth.** New `lib/internal-auth.ts`: constant-time compare of `x-internal-token` vs `INTERNAL_SERVICE_TOKEN`; read `x-beans-tenant` as the pinned owner; NEVER a model arg. Used by the internal routes and the new stage branch.
3. **Stage second branch.** In `web/app/api/ops/stage/route.ts`, before `auth()`, branch on `x-internal-token`: authenticate by service token, take owner/turnNonce from `x-beans-turn`/tenant header, call `stageOperation` (already headless-callable). Session branch unchanged.
4. **Re-home MCP base URL.** `beans-mcp.mjs` needs almost no HTTP-layer change: `callRead`/`callPreview` already send the right headers and fail-closed egress. Only the **paths** change (`/internal/ops/*` -> `/api/internal/ops/*`; previews already hit `/internal/ops/preview/*` -> `/api/ops/stage` with `{operationType,args,utterance}` body shape). ~8 one-line path edits, no transport rewrite.
5. **Gateway client.** New `web/lib/gateway/client.ts` (`BEANS_AI_URL`+`BEANS_AI_SHARED_SECRET`) POSTing `/run-agent`, returning assistant text + the op_tokens staged this turn (see §6). `AbortSignal.timeout` like `parse/client.ts`.
6. **Chat route swap.** Replace `parseMessage` with the gateway client; keep `fallbackParse` as the fallback arm. Pass the real operator utterance as the prompt so `stageOperation`'s `groundingCorpus` (from `flow-turns.ts`) still gates auto-post — the model's tool args are NOT the grounding source.
7. **Wire cards/auto-post/undo** to the gateway response shape (chat.tsx untouched if the envelope matches 009).

Cohort A: tasks 1-4 (read proof). Cohort B: 5-7 (write + UI).

## 6. The one thing only I noticed
`/run-agent` returns `{ok, path, text}` — a single string. But `callPreview` **strips `op_token` before returning to the model** (D-040, beans-mcp.mjs:311). So the token the confirm card needs is never in the gateway text. The route cannot read it from the response. The only correlation seam is the per-turn nonce already pinned into the child env (`BEANS_TURN_NONCE`) and stamped onto `pending.stage`. Therefore the chat route must, after the gateway turn, **query `pending_ops` by `(owner, turnNonce)`** to recover the staged op_token(s) and their verdicts out-of-band — the response contract is richer than today's single-proposal shape (a turn can stage zero, one, or several). Second, bounded: the gateway's agent timeout is 120s and `runAgentTurn` spawns a cold child (no warm pool on the agent path); a synchronous Vercel function will time out unless the route sets `maxDuration` high and `--max-turns` stays tight (6).

---
Summary line 1: The re-home is wiring, not rebuild — gateway `/run-agent` and the MCP tools already exist; the real work is new `/api/internal/ops/*` routes, a service-token branch on `/api/ops/stage`, and a gateway client swapped in for `parseMessage`.
Summary line 2: The trap: op_tokens are stripped from the model, so the route must recover them from `pending_ops` by the per-turn nonce, and must raise `maxDuration` to survive a cold multi-turn child under the Vercel timeout.
