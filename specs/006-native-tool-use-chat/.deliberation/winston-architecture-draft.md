---
spec: beans-native-chat · mode: update (ARCHITECTURE.md) · author: Winston · next: D-029
---

# Architecture draft: native tool-use chat (spec 006)

Decisions from replacing the Gemini LangGraph Timonel with a native Claude tool-use brain on the warm gateway. Addendum; D-001 through D-028 untouched except as named.

## 1. System shape

The brain swaps inside an unchanged seam: the route `/api/tenants/{phone}/chat`, the `{response, metadata}` envelope, the `chat_widget.js` mount in `cc_base.html` (D-028), the per-phone history buffer and the `tenant_context(phone)` scope all stay. `ChatService.chat_with_tenant` stops calling the LangGraph and drives a Claude tool-use loop on the gateway (`deploy/gateway.mjs`): one `claude` child per request, only a narrow MCP tool server enabled, every built-in denied. Those tools hold no DB credentials; each calls back to an authenticated operation API in FastAPI, which re-validates and runs under `tenant_context`. Reads return data; writes never commit from the loop, they stage a validated preview, and a human click on a confirm card commits through a separate operator-authenticated endpoint the model cannot reach.

| Module | Owns |
|--------|------|
| gateway (beans-ai) | warm pool, tool allowlist, turn cap, one child per request |
| beans MCP server | tool schemas, per-request tenant scope |
| internal operation API (FastAPI) | DB access, `tenant_context`, op_token store |
| confirm-commit endpoint | the single write capability |
| ChatService (brain) | system prompt, session phone, envelope, history |

Retired: `graph.py`, `agents/*`, the `llm.py` Gemini coupling. Reused: `llm_gateway.py` and the `INTERNAL_SERVICE_TOKEN` seam (`backend/auth/dependencies.py`).

## 2. Decision log

### D-029: Chat brain is a native tool-use loop on the gateway; the LangGraph is retired

- **Chosen.** Replace the body of `ChatService.chat_with_tenant` with one tools-enabled gateway loop. Delete `graph.py` and `agents/*`.
- **Alternatives / why lost.** Keeping the graph and re-pointing one node to tools keeps every fragile classification hop; an app-mediated loop (my prior recommendation) was overruled by Dario on 2026-10-16. One reasoner over a fixed tool set removes the router and resolver drift specs 001-002 fought.
- **Implications.** D-022 COST_SCENARIO becomes a read tool; D-018 PRODUCTION_UPDATE routes into the same brain. **Panel source.** Winston, grounding Dario.

### D-030: Tools are a narrow MCP server; built-ins disallowed; only `mcp__beans__*` allowlisted; no skip-permissions

- **Chosen.** The child runs `--max-turns` > 1 with `--allowedTools mcp__beans__*` plus the existing built-in `--disallowedTools` list, still omitting `--dangerously-skip-permissions`. One child per request, disposed after.
- **Alternatives / why lost.** skip-permissions with a disallow list is one typo from a built-in running; tools off is the retired design. Allowlisting only our tools and omitting skip-permissions denies anything off the list for lack of a TTY: two gates.
- **Implications.** Pool lifecycle moves to per-request; warmth and isolation hold since each request gets a fresh disposed child. **Panel source.** Winston, grounding Tamir.

### D-031: Tools hold no DB creds; they call an authenticated internal operation API; side effects observed there

- **Chosen.** Tools call back to FastAPI internal endpoints gated by `INTERNAL_SERVICE_TOKEN` (the existing `_has_internal_token` seam), which run the operation under `tenant_context`. Cache invalidation and navigation are emitted at commit, not parsed from gateway output.
- **Alternatives / why lost.** DB creds on the box put a leaking surface one injection from the ledger; letting the brain report side effects trusts effects an injection can fabricate. The box stays a pure reasoner; the app that owns the DB owns re-validation and every side effect, where it already does `tenant_context` and `cache.invalidate_all`. **Panel source.** Winston, with Amelia on reusing the endpoint contracts.

### D-032: Tenant scope is injected out of band, never a model-settable tool parameter

- **Chosen.** The gateway pins the session-resolved phone into the per-request MCP server environment; tools carry it on the callback, the model never sees or sets it, and FastAPI re-validates scope every call.
- **Alternatives / why lost.** `phone` as a model-filled argument is the injection target itself; hardcoding the one phone blocks the multi-tenant future for no gain. A scope the model cannot express is a cross-tenant surface that cannot be injected, now and later. **Panel source.** Winston, grounding Tamir.

### D-033: Writes are two-phase; commit is a non-model, operator-clicked endpoint

- **Chosen.** Write tools only stage a validated preview and mint an `op_token` in the server-side pending store (reusing D-008, D-010). The model surfaces it as a confirm card. Commit happens only on the operator's click, posting the token to a session-authenticated `/chat/confirm` endpoint the model has no tool for.
- **Alternatives / why lost.** A commit tool the model calls lets an injected confirmation fire it; direct commit inside the loop has no human gate. If commit is a tool, the injection-to-write surface spec 005's council closed stays open; removing it from the model's capability set means a hijacked model can only propose.
- **Implications.** The confirm card is a new `metadata` variant on the unchanged envelope, rendered by `chat_widget.js`, reusing D-009. **Panel source.** Winston, with Edut on consent and Tamir on the write boundary.

### D-034: Single business resolves the phone from the session; the brain ignores any client-supplied phone

- **Chosen.** The URL keeps `{phone}` for route compatibility, but for scope the brain uses the phone `require_tenant_match` already resolved from `beansco_session`, ignoring the path value.
- **Alternatives / why lost.** Trusting the URL `{phone}` is a client-controlled scope input; dropping it now needlessly breaks a deployed widget. The session is already the authority. **Panel source.** Winston.

## 3. Conventions

- **Tool naming.** `mcp__beans__<verb>_<noun>`: reads `read_*`, write previews `preview_*`. There is no `commit_*` tool.
- **Internal API shape.** `POST /internal/ops/{op}` under internal-token auth, 1:1 with the `database_config.py` functions, tenant from the pinned scope not the body. Previews return `{op_token, preview, missing_fields}`; reads return the module snapshot shapes.
- **Error handling.** Tools never raise into the loop; a failed callback returns a structured error the model relays as copy.
- **How writes confirm.** Preview stages, human clicks, `/chat/confirm` consumes the single-use token under `tenant_context`: the only place a row commits and the cache invalidates. One writer per fact: the internal API owns committed rows, the pending store owns staged intent, the summary is built from returned rows.

## 4. Non-goals

- No built-in tools ever, no DB creds on the box, no commit capability exposed to the model.
- No change to the envelope, widget seam, auth or `tenant_context` beyond the confirm-card variant.
- No new operation types; this spec ports the existing menu, and no multi-tenant rollout (single business, scope injected as if many).

## 5. Open architectural questions

- **A-Q13.** Shared `INTERNAL_SERVICE_TOKEN`, or a per-request token scoped to one phone with a short TTL? Fallback: existing token with the pinned phone and FastAPI re-validation for M1; per-request minting if the callback path widens. (D-031, D-032)
- **A-Q14.** Does the confirm card need a server-issued nonce bound to the `op_token`? Fallback: session auth plus single-use token for M1; add a nonce if the confirm endpoint is ever reachable without the session. (D-033)
- **A-Q15.** Does `--max-turns` bound the loop, or is a per-request tool-call budget also needed? Fallback: cap `--max-turns` low, measure live, add a tool-call counter if a turn loops. (D-030)
- **A-Q16.** Keep the gateway `/run` path, or retire it with the graph? Fallback: keep `/run` tool-free beside the new path, retire once nothing calls it. (D-029)
