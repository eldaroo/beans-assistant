---
date: 2026-10-17
slug: 007-native-tool-use-chat
status: scoped
tracking_issue: eldaroo/beans-assistant#198
---

# Spec 007: Native tool-use chat for Beans & Co

## Problem

Beans & Co runs across three countries from scattered WhatsApp threads and the founder's memory. The command center exists and shows the state of the business, but the conversational assistant that sits in it (the old "Timonel") is a Gemini LangGraph pipeline of classification hops (decomposer, router, resolver, expander, write, read). Correctness drifts in those hops, every new operation costs another node and another fragile prompt, and for the Costos, Produccion, Logistica and Proveedores modules the chat is the only write path there is. The real problem is the friction between a thought and a recorded fact: the founder sells or spends while mobile, and logging it later means opening a module and filling a form he skips. This spec replaces the old brain with one Claude reasoner that drives a narrow, fixed set of real Beans operations as native tools, coupled directly to the command-center database, so the founder can run the business by talking to it and never wonder whether it actually happened.

## Why now

The warm Claude-subscription gateway (`deploy/gateway.mjs`, Nomad job `beans-ai`) is already built, tested, and branded for Beans; it only needs a dedicated token to deploy. Spec 005 pointed the old graph at that gateway but kept the graph; Dario has now decided the old multi-agent Timonel should not exist at all. Building the native-tool-use chat now retires two brains down to one, lands it on infrastructure that already exists, and gives the command center the conversational capture surface it was designed to host.

## The binding decision

Dario chose, on 2026-10-16, native Claude tool-use on the gateway box over an app-mediated tool loop. That choice is binding. This spec does not re-litigate it; it makes a tools-enabled box defensible. The architecture (Winston, D-034 through D-039) is: a native tool-use loop replaces the LangGraph inside the unchanged chat seam; the only tools are a narrow MCP server (`mcp__beans__*`), every built-in tool stays denied, and `--dangerously-skip-permissions` is never passed; the tools hold no database credentials and call back to an authenticated internal operation API that re-validates under `tenant_context`; tenant scope is pinned out of band and is never a model-settable parameter; and writes are two-phase, where the model can only stage a preview and the commit happens through an endpoint the model has no tool for.

**Write-model refinement (2026-10-20, D-040 through D-044).** The binding native-tool decision is unchanged. The *write confirmation model* was refined by a six-voice panel (Winston, Tamir, Kaze, Sally, Edut, Amelia) convened because confirm-on-every-write did not replicate the wal-ledger ("Walter") agent Dario asked to model, and because a confirm on every write trains reflex-clicking that hollows the consent it exists to protect. The refined model, in one line: **reversible posts, irreversible asks.** A write auto-posts instantly with a loud Undo — the client auto-submitting the same non-model `/chat/confirm` — only when the server has proven it reversible, within caps, and grounded in the operator's own words this turn; everything irreversible, bulk, ambiguous, or un-grounded keeps the visible operator-clicked confirm card. The commit is never a model capability either way. Provenance and "obvious vs ask" are computed server-side, never claimed by the model (D-041, D-042). See D-040–D-044 in `ARCHITECTURE.md`.

## Scope

In scope:

- A native Claude tool-use loop on the warm `beans-ai` gateway (narrow MCP tools only, built-ins denied, no skip-permissions, `--max-turns` raised, one child per request then disposed), driving the chat inside the unchanged route, envelope, widget, history, and `tenant_context` seam.
- A beans MCP server exposing only Beans operations, with the single-business tenant pinned out of band.
- An authenticated internal operation API in FastAPI, 1:1 with the existing `database_config` operations, re-validating every call and carrying forward the domain guards that live in `write_agent` today (the NULL-price block, batch partial-success summaries, ADD_STOCK disambiguation, product resolution and SKU generation).
- Read tools for stock, revenue, profit, sales summary, the eight command-center module snapshots, and a `business_status` tool that reads the existing attention aggregation (`attention_service.py`), not a second opinion.
- Two-phase writes: preview tools that stage a server-side `op_token`, and a non-model confirm/commit endpoint (`/chat/confirm`) that is the single write capability, covering the full existing operation menu. The operator's click is auto-satisfied by the client for the reversible, operator-grounded, in-cap set (D-040); the commit itself is never a model capability.
- A server-computed `auto` verdict: provenance (the staged args appear verbatim in the operator's utterance this turn — ported from wal-ledger's `numberTokens`) and resolution determinism (exactly one active product candidate, amount verifies against a numeral) decide auto-post vs confirm card. Computed by the app, never by the model (D-041, D-042). A bare confirmation ("ok", "dale") never auto-posts.
- A clean, append-inverse Undo for the reversible set: `cancel_sale`/`cancel_expense` reworked from destructive DELETE to append-inverse voids (matching `cancel_stock_movement`), invoked by the Undo toast through a pre-authorized system path, with a pessimistic receipt that renders only on commit success (D-043).
- A confirm card in the chat widget, reserved for the irreversible, bulk, ambiguous, or un-grounded write (D-044), visually distinct from a completed receipt, showing parsed numeric values in digits, flagging irreversibility, settling in place on commit, and routing attention to the right tile.
- Security controls: a boot-time tool-posture self-check, a single-business read-plus-propose scoped operation-API bearer, per-session and global tool-call rate limits (tighter on cancellations and deactivations), an egress firewall, an append-only audit log of every tool call and every write intent, and an injection-corpus test.
- Retirement of the old Timonel (`graph.py`, `agents/*`, the Gemini coupling in `llm.py`), keeping `llm_gateway.py` and the salvaged operation logic.
- Live deploy on `beans-command-center.mdlautomations.duckdns.org` with the dedicated beans token, verified end to end.

Out of scope:

- Multi-tenant rollout. One business only (`+5491100000001`), with scope injected as if there could be many so the kernel stays reversible.
- New operation types beyond the existing menu. This ports the menu, it does not grow it.
- The onboarding chat (`/api/onboarding/web`), which stays a separate Gemini `.bind_tools` dispatcher.
- WhatsApp or any channel other than the command-center web slot.
- Replacing the command-center tiles or forms. The chat is a mouth and an ear for a surface the founder already has, not a second surface.

## Acceptance criteria

1. Gateway posture: with the native path enabled, `deploy/gateway.mjs` spawns each `claude` child with `--allowedTools mcp__beans__*`, the full existing built-in `--disallowedTools` list, `--strict-mcp-config`, `--max-turns` greater than 1, and no `--dangerously-skip-permissions`; `deploy/gateway.test.mjs` asserts each of these flags is present or absent as stated and is green.
2. Boot self-check: the gateway entrypoint asserts at boot that the only allowed tools match `mcp__beans__*` and exits non-zero otherwise, symmetric with the existing secret-shape grep; a unit test drives both the pass and the fail-closed path.
3. One child per request: a `/run` request that triggers a tool call leases one child, runs the multi-turn loop, and disposes that child after the response; a test asserts the child is gone and the pool refills.
4. Internal operation API: every read and every write-preview endpoint is reachable only with the internal token, binds the tenant from the pinned single-business scope (never from the request body), and re-validates its inputs with Pydantic under `tenant_context`; a cookie-less, token-only request returns the expected JSON and a request without the token returns the named-error envelope.
5. Read round-trip: a stock question posted to `/api/tenants/{phone}/chat` returns the live stock number sourced through the MCP read tool and the internal API, with the `{response, metadata}` envelope unchanged and `graph.py` not imported.
6. business_status single source: the `business_status` tool's "what needs attention" answer is byte-equal to the list `attention_service.aggregate()` plus `prioritize()` produces for the same tenant at the same time; a test feeds a fixture and asserts equality.
7. Two-phase spine: every write tool stages a validated preview and an `op_token` in the pending store and commits no row; `/chat/confirm` (session-authenticated) is the single commit path; the model has no tool that reaches it, whether the click is manual or client-auto-submitted. A double post is idempotent and the commit returns the committed values read back from the database.
8. Auto-post for the reversible, grounded, obvious write: a "registrá una venta por 400 de una tabla" message, where the amount matches a numeral in the utterance and the product resolves to exactly one active candidate, is committed immediately by the client auto-submitting `/chat/confirm` (metadata `auto:true`, set by the server, never the model), with a loud Undo toast and no manual click; the `sales` table has exactly the one row and the receipt renders only on commit success.
8b. Server-computed auto verdict: the `auto` flag is set only when the app proves (a) the op is in the reversible set {REGISTER_SALE, REGISTER_EXPENSE, ADD_STOCK}, (b) every load-bearing argument (amount numeral, unit price, product, counterparty) appears verbatim in the operator's utterance this turn, (c) the product resolves to exactly one active candidate, and (d) the write is within per-write and per-session caps; a tool-result-sourced instruction, a multi-candidate product, a NULL price, or a bare-confirmation turn ("dale") yields `auto:false` and a confirm card. A test drives each falsifying case.
9. No model self-confirm: an injection-corpus test in which a read tool returns tenant text that instructs a write proves no write commits without a human post to `/chat/confirm`, and an attempt to invoke any built-in tool is denied.
10. Confirm card distinct and honest: for a confirm-only write (D-044) the proposed-operation card renders as a visually distinct species from the committed receipt (provisional versus settled), shows numeric arguments in digits, surfaces an irreversibility flag, and on commit **settles in place** (it does not vanish and respawn as a receipt); the post-commit acknowledgement names the SKU or target, the amount, and the resulting balance from the commit response. The auto-post path (AC8) never shows this card — it lands an instant receipt with an Undo toast — so the operator learns the two species are different; verified in a live browser click-through at 360px and desktop.
11. Human-review surfaces: every CANCEL_SALE, CANCEL_EXPENSE, CANCEL_STOCK, CANCEL_LAST_OPERATION, DEACTIVATE_PRODUCT, UPDATE_PRODUCT_PRICE, REGISTER_PRODUCT, REGISTER_PRODUCT_WITH_STOCK, and REGISTER_PRODUCTS_BATCH path shows the exact target row (or an itemized set, for the batch) before commit and is stamped requires_human_review; the batch confirms once for the whole set, not once per item. An otherwise-reversible write that fails the auto verdict (AC8b) falls through to the same card.
12. Audit and limits: every tool call is written to an append-only audit log (name, arguments, caller, confirm-token, commit or deny), per-session and global tool-call caps hold with tighter caps on cancellations and deactivations, and box egress is firewalled to the operation-API host and Anthropic only; tests drive the cap and a blocked egress.
13. Old Timonel retired: `graph.py`, `agents/router|decomposer|expander|resolver|safe_node|state`, and the Gemini builders in `llm.py` are removed, no Gemini import remains, `llm_gateway.py` and the salvaged operation logic stay, and the existing chat-service and gateway test suites are green.
14. Live on prod: the `beans-ai` gateway and the command center are deployed to `beans-command-center.mdlautomations.duckdns.org` with the dedicated beans token; `GET /health` is green over TLS; in prod a read matches a command-center snapshot and a confirmed sale appears in the Ventas module.
15. Clean reversible undo: REGISTER_SALE, REGISTER_EXPENSE, and ADD_STOCK each reverse by an append-inverse void — `cancel_sale` and `cancel_expense` reworked from destructive DELETE to append-inverse (matching `cancel_stock_movement`) — fired by the Undo toast through a pre-authorized system path (not an operator-initiated CANCEL, which is itself confirm-only); the reversal is idempotent on a double tap, preserves the original and the voiding audit rows, and returns the affected per-book balance to its pre-write value to the cent; a test drives post → Undo → balance equality and a double Undo.
16. Pessimistic auto-post: when `register_sale`'s stock-availability guard rejects an auto-submitted sale, the operator never sees "anotado" — the receipt renders only on a 2xx commit, and the reply names why it could not post; a test drives a stock-guard rejection and asserts no receipt and a clear failure message.
17. Undo visibility invariant: every auto-posted write shows an Undo affordance that is a tap target of at least 44px, persists at least 6 seconds, sits above the composer at 360px, and names the reversal ("Anotado −$200 · Deshacer"); a test asserts presence, target size, and lifetime.

## Whole-problem surface

```yaml
surface:
  - id: s-01
    surface: Gateway native-tool posture (allowlist mcp__beans__*, built-ins denied, no skip-permissions, strict-mcp-config, max-turns, one child per request, boot tool-posture self-check)
    covers_by: M1
  - id: s-02
    surface: Beans MCP server (narrow tools, single-business tenant pinned out of band, never a tool argument)
    covers_by: M1
  - id: s-03
    surface: Authenticated internal operation API (internal-token gated, re-validation under tenant_context, salvaged write_agent domain guards)
    covers_by: M1
  - id: s-04
    surface: Read tools and business_status (stock, revenue, profit, sales summary, 8 module snapshots, attention from the single existing aggregation)
    covers_by: M2
  - id: s-05
    surface: Two-phase write (preview tools stage op_token) with /chat/confirm the single non-model commit capability; the server-computed auto verdict (provenance via numberTokens + resolution determinism) that auto-submits the reversible/grounded/obvious write and routes everything else to the card (D-040, D-041, D-042)
    covers_by: M3
  - id: s-06
    surface: Write-feel UX (instant receipt + loud Undo for auto-post; the confirm card as a distinct provisional species that settles in place on commit, digits read-back, irreversibility flag, navigation cue, mobile 360px); the safe path never shows the card (D-040, D-044)
    covers_by: M3
  - id: s-11
    surface: Clean reversible undo (cancel_sale/cancel_expense reworked DELETE to append-inverse; system-path compensator, not operator CANCEL) and pessimistic auto-post (receipt only on commit success; register_sale stock-guard post-hoc rejection) (D-043)
    covers_by: M3
  - id: s-07
    surface: Security hardening (scoped read-plus-propose bearer, rate limits, egress firewall, audit log, injection-corpus test)
    covers_by: M4
  - id: s-08
    surface: Consent controls (requires_human_review on irreversible, bulk, and ambiguous writes; confirm-only bucket extended to UPDATE_PRODUCT_PRICE and product registration; exact-target display, irreversibility flag, parsed-number read-back) (D-044)
    covers_by: M4
  - id: s-09
    surface: Old-Timonel retirement (remove graph.py, agents/*, Gemini llm.py; keep llm_gateway.py and salvaged logic)
    covers_by: M5
  - id: s-10
    surface: Live deploy on beans-command-center with the dedicated beans token, verified end to end
    covers_by: M6
    external: operator-credential
    tracking: eldaroo/beans-assistant#157, eldaroo/beans-assistant#158
```

## Open questions

1. Does `--allowedTools mcp__beans__*` auto-approve our MCP tools in headless `-p` (no TTY) without forcing `--dangerously-skip-permissions`? This is the load-bearing spike and gates the whole arc. Answerer: build spike (M1, first task). Default if it does not auto-approve: use a settings-based or MCP-approval auto-allow scoped to only our tools, never a blanket skip-permissions; if that is impossible, stop and surface to Dario rather than open the box.
2. Shared `INTERNAL_SERVICE_TOKEN` or a per-request short-TTL token scoped to one phone (Winston A-Q13)? Answerer: Tamir plus Winston. Default: existing token with the pinned phone and FastAPI re-validation for M1, per-request minting if the callback path widens.
3. Does the confirm card need a server-issued nonce bound to the `op_token` (A-Q14)? Answerer: Tamir. Default: session auth plus a single-use args-bound token for M1; add a nonce if `/chat/confirm` is ever reachable without the session.
4. Does `--max-turns` alone bound the loop, or is a separate tool-call budget needed (A-Q15)? Answerer: Amelia plus Tamir. Default: cap `--max-turns` low, measure live, add a tool-call counter if a turn loops.
5. Keep the gateway `/run` tool-free path beside the new tool path, or retire it with the graph (A-Q16)? Answerer: Winston. Default: keep `/run` tool-free until nothing calls it, then retire.

## Panelists who contributed

- Winston (BuildOS architecture): the system shape and decisions D-034 through D-039, including the two-phase write that keeps commit out of the model's hands.
- Amelia (BuildOS dev): implementation feasibility, the headless-MCP-flags spike, and the finding that `write_agent` carries domain guards that must be salvaged into the internal API, not deleted.
- Bob (BuildOS scrum master): the milestone arc and the insistence that M1 is a demonstrable vertical slice, not plumbing.
- Kaze (creative direction): the two card species, silent reads, and the materiality split that keeps a proposal from looking like a receipt.
- Edut (BusinessOS moral peer): the four Action Gates, the parsed-number read-back, and the requires_human_review stamps on irreversible and bulk writes.
- Tamir (SoulOS Rooted Shield): the threat model for a tools-enabled box, the boot tool-posture self-check, the server-authoritative confirm token, and the injection-corpus test.
- Compass (strategy and EOS): the product discipline that keeps the first version to log-a-sale, log-an-expense, and ask-status, and ties attention to the single existing aggregation.

### 2026-10-20 write-behavior panel (D-040 through D-044)

Convened to decide whether the chat faithfully replicates the wal-ledger ("Walter") agent and to re-examine the three write rules (A: native tool-use on the box; B: tools hold no DB creds; C: confirm every write). Unanimous: keep A (contained), keep B (load-bearing, independent of re-validation), reshape C to "reversible posts, irreversible asks."

- Winston (architecture): commit stays out of the model; auto-post is the client auto-submitting `/chat/confirm`; provenance must be server-recomputed; the compensator-deadlock catch (Undo must not route through a confirm-only CANCEL).
- Tamir (threat model): provenance is not self-certifiable (*provenance laundering*); the app must diff staged args against the operator's literal utterance this turn; Undo is not a substitute for confirm against injection; a bare "ok" never auto-posts.
- Kaze (creative): confirm-everywhere violates BREATH/SILENCE; friction is earned only at WEIGHT (the irreversible); the provisional card must settle in place.
- Sally (UX): confirm fatigue trains reflex-clicking that rubber-stamps the one dangerous write; the safe path must skip the card entirely; the unsure signal is server resolution-determinism, not model confidence.
- Edut (moral peer): vetoes both poles; the operator's utterance is sufficient consent for a reversible write iff Undo is a true, visible, durable reversal; the dividing line is irreversibility.
- Amelia (dev): no per-field confidence in a tool-use loop → use single-active-candidate + numeral-verify; cancel_sale/cancel_expense are destructive DELETE and must be reworked to append-inverse; register_sale can reject post-hoc → pessimistic post. The whole two-phase spine from M1 survives.
