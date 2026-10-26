# Winston review — Spec 010 (rescoped): revive spec-007 native tool-use on Vercel/Neon

**1. What problem is this actually solving?**
Breadth of interpretation, not write safety. Spec 009's propose-only parser dead-ends on anything outside its N fixed ops, so Timonel feels *tonto*. A reasoner that reads the whole message and sees its tools (Quinn-in-Discord) restores that. Crucially, the write *spine* spec 009 built — server-computed verdict, two-phase stage/confirm, server-authenticated grounding — is good and stays. We are swapping the brain in front of the spine, not the spine.

**2. Smallest first version on the new stack.**
M1, one vertical slice, zero parser change: a `/api/internal/ops/*` route family on Next with service-token auth; `read_stock` wired to the domain read and `register_sale` wired to `stageOperation`; point the gateway's `BEANS_OPS_URL` at the Next app. Prove end to end: gateway `/run-agent` → MCP tool → Next internal → `pending_ops`, with the chat route reading the `op_token` back by the turn nonce it minted and rendering one confirm card. The `/run-agent` loop, posture self-check, egress guard, and MCP tool shapes already exist on the box — M1 is mostly the Next internal API plus the read-back.

**3. Three risks that would kill this.**
(a) **Serverless timeout.** The Vercel route calls the Nomad loop synchronously; the agent turn budget is 120s today, Vercel caps a function far lower. Unbounded, the chat 504s. Mitigation: tighten the agent budget under `maxDuration`, fall back to the parser on timeout.
(b) **Grounding bypass.** If the internal preview endpoint grounds against the *model's tool args*, a model-invented numeral auto-posts. The utterance and corpus fed to `computeVerdict` must come only from the server's `operator_turns` record keyed by the out-of-band `(owner, flowNonce)` — never from anything the model passed.
(c) **Tenant / service-token pinning.** If the internal route trusts `x-beans-tenant` as arbitrary, or the token leaks, it is a cross-tenant write path. Tenant validates against the single-business allowlist; token constant-time compared; the route family is isolated from the session routes.

**4. Success at 90 days.**
Free-form, multilingual, compound turns and mixed read+write in one message all land. Reversible, grounded, obvious writes auto-post with a loud Undo; everything else shows a confirm card. Zero model-committed rows (proven by the injection corpus). The propose-only parser fires only as a rare degrade path, not the brain. One live business, reversible to multi-tenant because scope is still out of band.

**5. Atomic tasks (milestone cohorts, each ≤10, ≤1 day/child).**
- **M1 — internal API + vertical slice:** service-token guard; tenant validation; `read_stock` endpoint; `register_sale` preview endpoint → `stageOperation`; gateway `BEANS_OPS_URL` repoint; op_token read-back by turn nonce; one card rendered.
- **M2 — read surface + reversible previews:** `read_revenue`, `read_profit`, `read_sales_summary`, `read_module`, `business_status`; `register_expense`, `add_stock`.
- **M3 — chat-route swap:** `parseMessage` → gateway `/run-agent`; parser demoted to fallback on gateway failure/timeout; `maxDuration` + fetch-timeout budget; auto-post / Undo / card parity with spec 009.
- **M4 — confirm-only previews + consent gate:** `update_product_price`, `register_product`, `register_products_batch`, `deactivate_product`, `cancel_last_operation`; retain D-057 multi-turn-confirm.
- **M5 — security on the re-homed path:** injection-corpus test, egress now the Next host, service-token denial, caps (tighter on cancels/deactivations), audit of every tool call.
- **M6 — retire the slot-filling draft; live deploy + end-to-end verify.**

**6. The one thing only architecture noticed.**
The `op_token` cannot travel through the gateway response *or* the model — `callPreview` already strips it by design. So the route's only coherent way to obtain commitable handles is to read `pending_ops` back by the `turnNonce` it minted and injected out of band (`verdictPendingForTurn` already exists). The gateway returns prose; Neon returns the handles. That inversion is the seam that keeps two-phase intact across the box boundary, and it is invisible unless you trace who is allowed to hold the token.
