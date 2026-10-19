# Bob review (Scrum Master): sequencing and the smallest honest first version

## 1. What problem is this actually solving

Give the operator one trustworthy conversational way to read and change the business, on the warm Claude gateway the team already runs, and stop maintaining two brains. The chat is still the only write path for costos, produccion, logistica, and proveedores, so retiring it is not optional until native tool-use replaces it.

## 2. The smallest first version that proves the idea

One read tool round-tripping end to end. The operator asks "how much stock", the gateway child calls a single MCP `get_stock` tool, which calls the authenticated internal endpoint, the app queries under session tenant scope, and the number returns to the chat. No writes, no second tool. If that loop is clean, native tool-use is proven and the rest is repetition.

## 3. Three risks that would kill this

- Tools reopen the injection-to-write surface spec 005 closed. If writes are not strictly behind the confirm card, one injection commits a sale. This gate has to hold.
- The child lifecycle change (one child per request, disposed after) can leak tenant state or drain the warm pool. Dispose-after must be verified, not assumed.
- The dedicated beans token (#157/#158) is the one external gate. Sequence around it, do not block the arc on it.

## 4. Success at 90 days

Operator runs the business from the chat daily, graph.py and agents/* gone from master, zero writes committed without a confirm, no Gemini dependency remaining, read answers matching the live module snapshots.

## 5. Atomic tasks, grouped by milestone (dependency order)

M1 (smallest first version, prove the loop):
1. Internal read op API: one authenticated `get_stock` endpoint, session tenant scope, re-validated. Accept: cookie'd curl returns stock JSON for +5491100000001.
2. MCP server skeleton exposing only `get_stock`. Accept: tool list shows one tool, manual invoke returns stock.
3. Gateway reconfig: narrow MCP on, built-ins disallowed, max-turns>1, one child per request then disposed. Accept: /run stock question fires one tool call, child disposed after.
4. Wire chat_service to the tool loop inside the unchanged seam. Accept: POST .../chat returns stock without touching graph.py.
5. Dedicated beans token plus fail-closed allowlist. Accept: box boots only with beans token + bearer, no DB creds in env.

M2 (read tools, no writes):
6. Revenue/profit/sales-summary read tools. Accept: each matches its snapshot number.
7. Eight module-snapshot read tools (caja, productos, stock, ventas, costos, produccion, logistica, proveedores). Accept: per-module answer matches live snapshot.
8. Tool-selection prompt plus no-tool fallback. Accept: smalltalk returns with zero tool calls.

M3 (writes behind confirmation):
9. Confirm-card contract in the envelope (proposed op plus args, pending). Accept: a write request returns a card, no mutation.
10. Confirm/commit endpoint plus widget action, reusing the Wal pattern. Accept: confirm commits once, cancel discards, double-confirm idempotent.
11. Write tools 1:1 with database_config functions. Accept: each commits only post-confirm, re-validated server side.
12. Cancel tools including CANCEL_LAST_OPERATION behind the same gate. Accept: cancel requires confirm and reverses the named op.

M4 (retire old Timonel):
13. Delete graph.py, agents/*, Gemini coupling in llm.py; keep route, envelope, widget, tenant_context, llm_gateway.py. Accept: no Gemini import, tests green.
14. Record decision D-029 in ARCHITECTURE.md. Accept: old-Timonel section marked retired.

M5 (deploy and verify):
15. Deploy gateway job and command center to prod. Accept: /health green, chat live.
16. Prod check of one read and one confirmed write. Accept: read matches a snapshot, a confirmed sale appears in ventas.

## 6. The one thing only my faculty noticed

M1 must be a true vertical slice with a visible demo, not tool server plus gateway plumbing with nothing to see. Build the one read tool and its endpoint together so M1 ends with a working chat answer in prod-shaped form. If M1 is only plumbing, the team drains two cohorts before anyone sees the idea work, and the first honest feedback on tool-loop shape arrives too late to correct cheaply.
