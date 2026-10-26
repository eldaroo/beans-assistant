# Context packet — Spec 010 (rescoped): Timonel native tool-use chat, revive spec 007 on the Vercel/Neon stack (Nomad gateway + MCP)

**Target repo:** eldaroo/beans-assistant. **Base branch:** claude/008-vercel-migration (specs 008 and 009 live here). This supersedes the slot-filling draft. Each panelist writes against THIS packet to reviews/<panelist>-review.md, <=600 words, answering the six prompts at the end.

## Dario's decision (2026-10-26)

The propose-only parser (a single parse pass to one of N fixed ops, dead-ends on anything else) made Timonel "tonto". Dario wants to go BACK to spec 007 "native tool-use chat": an agent that understands the whole message and sees what tools it has, like Quinn-in-Discord. He chose the re-homing explicitly: run the tool-use loop on the Nomad gateway box with MCP, as spec 007 did literally, NOT an Anthropic-API loop inside the Vercel route.

## What spec 007 was (already deliberated, D-034..D-044, 6-voice panel Winston/Tamir/Kaze/Sally/Edut/Amelia)

A native Claude tool-use loop on the warm `beans-ai` Nomad gateway: each request leases one `claude` child with `--allowedTools mcp__beans__*`, all built-ins denied, `--strict-mcp-config`, `--max-turns > 1`, NO `--dangerously-skip-permissions`, one child per request then disposed. The MCP server exposes ONLY Beans operations (reads + write-PREVIEWS); tools hold NO DB credentials and call back to an authenticated internal operation API; the single-business tenant is pinned OUT OF BAND (never a model-settable arg). Writes are two-phase: a preview tool stages an op_token; the commit is a non-model endpoint the model has NO tool for. A SERVER-computed verdict decides auto-post vs confirm card: "reversible posts, irreversible asks" (reversible + every load-bearing numeral verbatim in the operator's own turn + single active product candidate + within caps -> auto-post with a loud Undo; everything else -> operator-clicked confirm card). Spec 007 shipped M1-M5 on the OLD Python/FastAPI stack; spec 008 then rebuilt Beans on Vercel/Neon and RETIRED the tool-use loop (D-046) in favor of the propose-only parser, because the `claude`-children loop did not port cleanly to serverless. The parser is why it is dumb now.

## The current stack (what exists, what to re-home)

- The gateway + MCP CODE still exist in the tree: `deploy/beans-ai.nomad.hcl` (the gateway Nomad job), `deploy/beans-mcp.mjs` (the MCP server, with read tools AND write-preview tools register_sale/register_expense/add_stock/update_product_price/register_product/register_products_batch/cancel_last_operation already defined), `deploy/beans-mcp.test.mjs`, `deploy/agent-mode.test.mjs`, `deploy/egress-guard.mjs`. But the MCP tools call the OLD FastAPI internal operation API, which no longer exists (008 replaced it with the Next.js app).
- The chat route (`web/app/api/chat/route.ts`) currently calls the propose-only parser via `parseMessage` (`web/lib/parse/client.ts`, env BEANS_PARSE_URL/BEANS_PARSE_BEARER -> the `beans-parse` Nomad job). The swap seam is this call.
- Spec 009 already built the WRITE-SAFETY SUBSTRATE on the Vercel/Neon stack and it must be REUSED, not rebuilt: `web/lib/ops/stage.ts` (`stageOperation`: re-derives resolution + grounded amounts + the verdict, stages a pending_ops preview, returns an op_token), `web/lib/verdict.ts` (`computeVerdict`: reversible/grounded/deterministic/within-caps), `web/lib/flow-turns.ts` (the server-authenticated, owner- and TTL-scoped operator_turns grounding record, D-052), `/api/ops/confirm` (the non-model commit), `/api/ops/undo`, the confirm cards + auto-post + Undo in `web/app/(app)/_components/chat.tsx`, the `web/lib/ops/registry.ts` OpDef menu (REGISTER_SALE, REGISTER_EXPENSE, ADD_STOCK reversible; REGISTER_PRODUCT, UPDATE_PRICE, DEACTIVATE_PRODUCT, CANCEL_*, RECORD_PRODUCTION, CREATE_SUPPLIER, RECORD_CHECKIN, EDIT_PRODUCT confirm-only), and the m7-injection corpus.
- `/api/ops/stage` currently requires a session (auth()). The MCP write-preview tools, calling from the Nomad box, need an INTERNAL service-token path (tenant pinned, no session), separate from the session path.

## The re-homing (what this spec must decide and build)

1. Point the chat route at the `beans-ai` tool-use gateway instead of the `beans-parse` parser (keep a fallback).
2. Re-home the MCP tools' internal operation API from the dead FastAPI to the Next.js app: read tools call the domain reads; write-preview tools call `/api/ops/stage` (which already re-derives the verdict and stages an op_token). Add an internal service-token auth path on the Next side; the tenant/owner is pinned out of band.
3. The gateway runs the tool-use loop (understand -> read/propose), returns the assistant text plus any staged op_token(s); the Vercel route renders the reply + the confirm cards / auto-post exactly as spec 009 does; the commit stays `/api/ops/confirm`.
4. Reuse verdict.ts (reversible posts / irreversible asks), the operator_turns grounding (the operator's own words this turn still gate auto), the confirm cards, the Undo. The model never commits.
5. Preserve all spec-007 security controls on the new stack: boot-time tool-posture self-check, built-ins denied, no skip-permissions, one child per request disposed, per-session and global tool-call caps (tighter on cancels/deactivations), egress firewall (operation-API host + Anthropic only), append-only audit of every tool call and write intent, and the injection corpus (a read tool returning tenant text that orders a write must not commit).

## Known tensions / open questions for the panel

- Latency and cost of a multi-turn `claude`-child tool-use loop on the Nomad box, called synchronously from a Vercel serverless function (the route's timeout).
- Grounding: spec 007's auto-verdict needs "the operator's own words this turn"; with a tool-use loop the model proposes write args via the stage tool. How does the operator's actual utterance reach `computeVerdict` so a tool-sourced or model-invented numeral cannot auto-post? (The stage call must carry the real operator turn; the 009 operator_turns record is the source of truth.)
- Internal auth: the shape of the service-token path on `/api/ops/stage` (and the reads) so the Nomad MCP tools authenticate without a user session, tenant pinned, never model-set.
- How much of `beans-mcp.mjs` (built for FastAPI) is reusable vs rewritten for the Next internal API.
- Cohorting: this is a large arc (gateway wiring + MCP re-home + internal auth + two-phase writes + verdict reuse + security controls + retire the parser path). Group into milestone cohorts of <=10 children each.

## The six prompts every panelist answers (<=600 words)
1. What problem is this actually solving?
2. What is the smallest first version that proves the idea on the NEW stack (e.g. one read tool round-trip through the gateway + MCP + Next internal API, then one write-preview)?
3. What 3 risks would kill this if ignored?
4. What does success look like at 90 days?
5. What atomic tasks does this break into? (list 5-15, each <= 1 day; group into milestone cohorts)
6. What is the one thing only your faculty would have noticed?
