# Amelia review — Beans native-tool-use chat (spec 006)

Angle: implementation feasibility.

## 1. What problem is this actually solving

The old brain is a Gemini classify-then-route chain (decomposer, router, resolver, expander, write/read, final_answer) sitting in front of 11 write functions. Every new operation costs a router-prompt edit, a resolver branch, and a graph edge. Native tool-use collapses router plus resolver plus decomposer into the model picking a typed tool. The real work is replacing an unmaintainable LLM orchestration layer with a tool contract the model drives, re-pointed at the command-center DB.

## 2. Smallest first version

One warm child per request, MCP tools enabled, built-ins disallowed, `--max-turns` > 1. An MCP server exposing THREE tools: `read_stock`, `read_revenue`, `register_sale`. Each calls a new internal ops API bound server-side to the fixed phone. `register_sale` STAGES and returns a proposal; the chat renders the Wal confirm card; a separate confirm call commits. That exercises the whole mechanic (tool loop, callback, re-validation, confirm gate, isolation) before porting the other ~17 tools.

## 3. Three risks that would kill this

1. Permission auto-resolve. In headless `-p` there is no TTY. If `--allowedTools mcp__beans__*` does not auto-approve MCP tools on its own, every call either hangs or forces `--dangerously-skip-permissions`, which throws away the built-in-denial guarantee the gateway relies on today. Spike this before anything else.
2. Confirmation cannot be mid-loop. A request/response gateway cannot pause a running child for a human click. If write tools commit directly, the injection-to-write surface is wide open. Writes MUST stage and return a proposal, then commit only on a separate confirmed call.
3. Tenant identity passed by the box. If a tool argument carries the phone, an injection can target another tenant. Identity must be bound to the internal token server-side, fixed to `+5491100000001`; the box never names the tenant.

## 4. Success at 90 days

Timonel-old deleted. All 11 writes plus the reads live as tools; every write passes the confirm card; zero DB creds on the box. The read-only command-center domains (costos, produccion, logistica, proveedores) gain a chat write path. Adding an operation is one internal endpoint plus one tool entry, no prompt surgery. `gateway.test.mjs` green; internal API has re-validation tests.

## 5. Atomic tasks

1. Spike headless MCP flags: allowedTools auto-approve, max-turns loop, stream-json tool events. 0.5d
2. Internal ops API router, bearer-gated, tenant bound to fixed phone, Pydantic re-validation. 0.5d
3. Port `write_agent` validation (NULL-price block, batch summary, ADD_STOCK disambiguation, navigation cue) into write endpoints that STAGE and return a proposal. 2d
4. Port `read_agent` SQL plus formatters and the 8 module snapshots into read endpoints. 1.5d
5. Confirm/commit endpoint and staging token for proposed writes. 0.5d
6. MCP stdio server, ~20 handlers each one internal-API call. 1d
7. `gateway.mjs`: one-child-per-request lifecycle, MCP config wiring, max-turns, disposal; keep pool, bearer, isolation self-check. 1.5d
8. Secret allowlist: add INTERNAL_API_BASE and INTERNAL_API_TOKEN; keep the keyring grep. 0.25d
9. Swap `ChatService.chat_with_tenant` to the gateway tool path; keep the history deque, drop the graph. 1d
10. Wal confirm card in `chat_widget.js` reading proposal metadata. 1d
11. Delete `graph.py`, `agents/*`, Gemini `llm.py`; prune imports. 0.5d
12. E2E on prod: one read, one staged write, confirm commit, verify row and cache invalidation. 1d

## 6. The one thing only I would have noticed

`write_agent.py` is not thin glue. Its body carries domain rules that are NOT in `database_config`: the pre-commit NULL-price block on REGISTER_SALE (`register_sale` will happily sell at a null price), the batch partial-success summary built from returned rows, the ADD_STOCK-versus-create disambiguation, and the resolver's `product_ref` resolution and SKU generation. If the spec treats `write_agent` as deletable and wires tools straight to `database_config`, those guards vanish and the model can commit a zero-price sale. Those rules move into the internal ops API; they are salvage, not scrap.
