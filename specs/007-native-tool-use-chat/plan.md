---
date: 2026-10-17
slug: 007-native-tool-use-chat
---

# Plan 007: Native tool-use chat for Beans & Co

Full decision log in `ARCHITECTURE.md`, D-034 through D-039.

## Architecture sketch

The brain swaps inside an unchanged seam. The HTTP route `/api/tenants/{phone}/chat`, the `{response, metadata}` envelope, the `chat_widget.js` mount, the per-phone history buffer, and the `tenant_context(phone)` scope all stay. `ChatService.chat_with_tenant` stops calling the LangGraph and drives a native Claude tool-use loop on the warm gateway. The gateway runs one `claude` child per request with only a narrow MCP tool server enabled and every built-in denied. The tools hold no database credentials: each calls back to an authenticated internal operation API in FastAPI, which re-validates and runs under `tenant_context`. Reads return data. Writes never commit from the loop; they stage a validated preview and mint an `op_token`, and the model surfaces that as a confirm card. The commit happens only when the operator clicks, posting the token to a session-authenticated `/chat/confirm` endpoint the model has no tool for.

```
operator -> chat_widget.js -> POST /api/tenants/{phone}/chat (envelope unchanged)
   -> ChatService.chat_with_tenant (system prompt, session phone, history)
      -> gateway /run  (one claude child per request, --allowedTools mcp__beans__*, built-ins denied, no skip-permissions, --max-turns>1)
         -> MCP tool call (tenant pinned out of band)
            -> internal operation API (internal-token, tenant_context, re-validate)
               -> read: returns data        -> back into the loop
               -> write: stage op_token      -> returns preview (no commit)
   <- {response, metadata: proposed-operation card | result}
operator clicks Confirmar
   -> POST /chat/confirm (session auth, single-use op_token)  [NO model tool reaches this]
      -> commit one row under tenant_context, invalidate cache, read back committed values
   <- {response, metadata: committed receipt + navigation cue}
```

Module ownership: the gateway owns the warm pool, the tool allowlist, the turn cap, and one-child-per-request. The beans MCP server owns the tool schemas and the per-request tenant scope. The internal operation API owns DB access, `tenant_context`, and the `op_token` store. The confirm/commit endpoint is the single write capability. ChatService owns the system prompt, the session phone, the envelope, and the history.

## Sequencing

### M1: Prove the loop end to end (covers s-01, s-02, s-03)

A demonstrable vertical slice, not plumbing. Spike the headless MCP flags first; reconfigure the gateway to the native-tool posture with the boot self-check; stand up the MCP server and one authenticated internal read endpoint; wire one `read_stock` tool; swap `ChatService` to the loop (read-only); resolve the business from the session cookie. Ends with a live chat answering a stock question through the full new path. Rough effort: 4 to 5 days.

### M2: Read tools, no writes (covers s-04)

Port the remaining reads (revenue, profit, sales summary) and the eight module snapshots as read tools, add `business_status` reading the existing attention aggregation, and add the tool-selection prompt with a no-tool fallback for smalltalk. The operation-API bearer is read-scoped here, so there is no write risk while the read surface is proven. Rough effort: 2 to 3 days.

### M3: Writes with the provenance split, reversible set (covers s-05, s-06, s-11; D-040 through D-044)

Build the two-phase write machinery AND the "reversible posts, irreversible asks" model on top of it:
- Internal write-preview endpoints that stage an `op_token` and carry the salvaged `write_agent` guards; the server-authoritative single-use confirm token; the `/chat/confirm` commit endpoint. (Already present from M1 — reuse.)
- The **server-computed `auto` verdict**: provenance (every load-bearing staged arg appears verbatim in the operator's utterance this turn — rebuild wal-ledger's `numberTokens`/no-number-left-behind in Python) plus resolution determinism (exactly one active product candidate from the existing lookup; amount and unit price verify against a numeral). Never a model field. A bare-confirmation turn yields `auto:false`.
- The preview tools for the reversible set (REGISTER_SALE, REGISTER_EXPENSE, ADD_STOCK) and the **client auto-submit** path in `chat_widget.js` that posts `/chat/confirm` on the operator's behalf when `auto:true`, landing an instant receipt with a loud Undo toast.
- **Prerequisite — clean reversible undo:** rework `cancel_sale`/`cancel_expense` from destructive DELETE to append-inverse voids (matching `cancel_stock_movement`); the Undo toast fires the compensator through a pre-authorized system path, not an operator CANCEL. Idempotent, audit-preserving, balance-restoring.
- **Pessimistic post:** the receipt renders only on a 2xx commit (`register_sale`'s stock guard can reject after the fact).
- The confirm-card variant for the `auto:false` fall-through, with the two visual species, settle-in-place on commit, and digit read-back.

Rough effort: 4 to 5 days (the auto verdict and the undo rework are the new work over a plain confirm-everything build).

### M4: Irreversible and bulk writes, hardening (covers s-07, s-08; D-044)

Add the remaining write-preview tools as **confirm-only** (D-044), never auto-post: products (REGISTER_PRODUCT, REGISTER_PRODUCT_WITH_STOCK), UPDATE_PRODUCT_PRICE (prior price not snapshotted → no clean undo), REGISTER_PRODUCTS_BATCH, and the cancel and deactivate tools — each showing the exact target (or an itemized set for the batch) and an irreversibility flag, stamped requires_human_review, the batch confirming once for the whole set. Add rate limits (tighter on cancel and deactivate) and the per-write/per-session caps the M3 auto verdict depends on, the audit log, the egress firewall, the scorecard counters, and the injection-corpus test (which now also asserts an injected write yields `auto:false` + a human-gated card, never a silent auto-post). Rough effort: 3 to 4 days.

### M5: Retire the old Timonel (covers s-09)

Delete `graph.py`, `agents/router|decomposer|expander|resolver|safe_node|state`, and the Gemini builders in `llm.py`; keep the route, envelope, widget, `tenant_context`, `llm_gateway.py`, and the salvaged operation logic now living in the internal API. Record the retirement in `ARCHITECTURE.md`. Rough effort: 1 day.

### M6: Deploy and verify on prod (covers s-10, external: operator-credential)

Deploy the `beans-ai` gateway with the dedicated beans token and the command center to `beans-command-center.mdlautomations.duckdns.org`, confirm `GET /health` green over TLS, and run a prod check of one read and one confirmed write. The one external gate is Dario minting the dedicated `claude setup-token` (eldaroo/beans-assistant#157, #158). Rough effort: 1 day once the token exists.

## Risks

1. Permission auto-resolve in headless. If `--allowedTools mcp__beans__*` does not auto-approve our MCP tools without a TTY, the only paths are a scoped auto-allow or a blanket `--dangerously-skip-permissions` that throws away the built-in denial guarantee. Mitigation: spike this as the first task of M1 and gate the arc on it; if no scoped auto-allow exists, stop and surface rather than open the box.
2. Injection to write. Tenant text now reaches a tool-enabled model. Mitigation: commit is not a model tool (D-033); a fully hijacked model can only stage a preview a human approves. Backed by the boot tool-posture self-check, the scoped bearer, and the injection-corpus test.
3. Salvaged guards lost. `write_agent` holds domain rules absent from `database_config` (NULL-price block, batch partial-success, ADD_STOCK disambiguation, product resolution, SKU generation). Mitigation: those move into the internal operation API with re-validation tests; they are salvage, not scrap (AC13 keeps them).
4. Scope sprawl and confirm fatigue. Wiring all operations at once, or demanding one tap per batch item, produces a copilot that earns no daily habit and trains reflex-clicking. Mitigation: M1 to M3 ship the three core jobs first (sale, expense, status); batch confirms once, itemized (AC11).
5. Latency and loop blow-up. A multi-turn loop per request is slower and can loop. Mitigation: keep the warm pool, cap `--max-turns` low, one child per request disposed, measure live, add a tool-call budget if a turn loops (open question 4).

## Dependencies

- The dedicated beans `claude setup-token` in the Nomad Variable `nomad/jobs/beans-ai`, minted by Dario (external: operator-credential; eldaroo/beans-assistant#157, #158). M6 only.
- The warm gateway infrastructure built in spec 005 (`deploy/gateway.mjs`, `deploy/build-hcl.mjs`, the `beans-ai` Nomad template) and the Python client `llm_gateway.py`, reused.
- The command-center modules and services (`backend/modules/*`, `backend/services/*`), the `INTERNAL_SERVICE_TOKEN` seam in `backend/auth/dependencies.py`, and the pending-operation store from D-008/D-010, reused.
- Confirmation of which branch prod runs (the single-business pivot is branch-only on master today); resolved as part of M6.

## Cost-shaped considerations

- Token cost per turn rises versus the old single classification call, because a tool loop replays the growing transcript to a fresh child each hop. Mitigate by capping `--max-turns` and keeping the tool set narrow.
- Attention cost: the whole value is the founder trusting the chat. One silent wrong commit spends that trust. The two-phase write and the digit read-back are the controls that protect it; they are not optional polish.
