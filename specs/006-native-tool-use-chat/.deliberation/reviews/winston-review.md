# Winston review — Beans native-tool-use chat (spec 006)

Native tool-use on the box is Dario's binding choice; my job is to make it safe, not re-open it.

## 1. What problem is this actually solving?

The Gemini LangGraph Timonel is a multi-call pipeline (decomposer, router, resolver, expander, write, read) where correctness drifts in the classification hops and extending it means another node and another fragile prompt. One brain cannot reliably drive the full operations menu, and for costos, produccion, logistica and proveedores the chat is the only write path at all. One Claude reasoner over a fixed tool set removes the router and resolver fragility and couples the assistant to the real command-center operations.

## 2. Smallest first version that proves the idea?

One read tool (current stock) and one write-preview tool (register_sale) wired through a new authenticated internal operation API, plus the human-clicked confirm-commit endpoint, on the gateway with our MCP tools allowlisted and every built-in denied, single business resolved from the session cookie. Prove end to end: a read returns live data, a sale previews as a confirm card, a human click commits exactly once, cache invalidates, the envelope is unchanged, an injected built-in call is denied. That proves the whole shape before porting the other eleven writes.

## 3. Three risks that would kill this if ignored

a. Injection to write. Tenant text now reaches a tool-enabled model. Closed only by keeping commit out of the model's hands (Q6), not by prompt hardening.

b. Token blast radius. A shared or long-lived credential on the box turns one injection into org-wide reach. Use the dedicated beans token, box holds no DB creds, callback scoped to one tenant.

c. Turn and latency blow-up. A multi-turn loop per request is slower and can loop. Cap max-turns, bound the tool set, keep the warm pool, one child per request disposed.

## 4. What does success look like at 90 days?

graph.py and agents/* are gone with the Gemini coupling; the native brain serves every read and write-preview in prod on beans-command-center; writes commit only by a human click; no cross-tenant leak under adversarial input; median turn within a few seconds; one assistant widget, no Gemini dependency.

## 5. Atomic tasks (each <= 1 day)

1. Gateway tools-enabled path: allowlist mcp__beans__*, built-ins disallowed, no skip-permissions, max-turns > 1, one child per request disposed.
2. Narrow MCP server scaffold: stdio, tenant phone pinned in env, not a tool argument.
3. Internal operation API reads: internal-token gated, tenant_context.
4. Internal operation API write-preview endpoints: validate, stage op_token, no commit.
5. Confirm-commit endpoint: session-auth, consume op_token, idempotent, cache invalidate, navigation.
6. MCP read tools calling task 3.
7. MCP write-preview tools calling task 4, returning confirm-card metadata.
8. Swap ChatService.chat_with_tenant brain to the gateway loop; keep envelope, history, tenant_context.
9. Confirm-card variant in chat_widget.js posting to task 5.
10. Single-business phone resolved from session; brain ignores client phone.
11. Remove graph.py, agents/*, llm.py Gemini coupling; keep llm_gateway.py.
12. Deploy beans-ai with the dedicated token, verify end to end.

## 6. The one thing only my faculty would have noticed

Commit must not be a model tool. If the model can call a commit tool, the injection-to-write surface stays open however hard the prompt is tuned. Make commit a non-model, operator-clicked endpoint and a fully hijacked model still cannot write: it can only stage a preview a human approves. That is an architecture boundary, not a mitigation, and it is the decision that makes a tools-enabled box defensible rather than hopeful.
