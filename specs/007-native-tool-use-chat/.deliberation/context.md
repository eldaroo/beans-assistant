# Context packet — Beans & Co native-tool-use chat (spec 006)

Run id: beans-native-chat-20261016-152645
Target repo: clients/eldaroo/beans-assistant (eldaroo/beans-assistant, master). target_kind = existing.
Architecture: mode = update on the repo's ARCHITECTURE.md. Next decision ordinal = D-029.

Every panelist writes against THIS packet, in their own voice, in their own review file. Six questions, 600-word limit.

## The raw idea (verbatim, from Dario)

Build a new conversational assistant for Beans & Co, modeled on "the chat we built for Walter" (a Claude-subscription warm-gateway assistant), coupled directly to the NEW Beans command-center surface and its real database and operations. This REPLACES and retires the old Gemini multi-agent Timonel. Quote: "construir un chat como el q le hicimos a walter, pero acoplado a la superficie nueva q creamos para beans & co y su base de datos y operaciones." Also: "timonel ya no deberia existir, por lo menos la version vieja." Single business, no test tenant. Quinn (me) builds, deploys to prod on beans-command-center, and verifies end to end. "hacelo todo vos, tenes acceso a todo."

## Dario's load-bearing architecture decision (already made, 2026-10-16)

I presented three paths for HOW the chat executes real operations. Dario chose **native tool-use on the box** over my recommendation of an app-mediated tool loop. His choice is binding. The spec builds native Claude tool-use.

The hardened reading of his choice (the panel's job is to make this safe, not to re-litigate it):
- Claude on the warm gateway box drives a real tool-calling loop (multi-turn within one user request).
- The ONLY tools that exist are a narrow, purpose-built set of Beans operations (an MCP server). Every built-in tool (Bash, Edit, Write, Read, Glob, Grep, WebFetch, WebSearch, Task) stays disallowed.
- The box holds NO database credentials and reads no tenant data directly. Each tool's implementation calls back to an authenticated internal operation API in the Beans app, which runs the real DB operation with re-validation and single-business tenant scope.
- Writes pass through a confirmation step (the model proposes, the operator confirms in the chat UI before commit). Reuse the Wal "confirm card" pattern.
- This reopens the injection-to-write surface that spec 005's council closed, so Tamir's threat model is central. The deliverable is a defensible tools-enabled box, not a veto.

## Grounding fact set (from two codebase sweeps; treat as accurate)

### What the old Timonel is (what gets retired)
- A Gemini-backed LangGraph multi-agent graph. Files: `graph.py` (create_business_agent_graph; decomposer -> router -> resolver/expander -> write/read -> final_answer), `agents/*` (router, resolver, read_agent, write_agent, decomposer, expander, safe_node, state, error_copy, field_labels, attributes, sku), and the Gemini coupling in `llm.py`.
- Retiring it = replacing the body of `backend/services/chat_service.py` `ChatService.chat_with_tenant` plus `graph.py` + `agents/*`. The HTTP route, the response envelope, the chat widget, and the `tenant_context` plumbing STAY. We swap the brain inside an unchanged seam.
- `llm_gateway.py` (the spec-005 Claude gateway client: ChatGateway, call_gateway, SafeDefaultChatModel) is REUSABLE, not retired.

### The operations menu (what the chat must be able to do)
- Writes (today dispatched by `agents/write_agent.py`, 1:1 with functions in `database_config.py`): REGISTER_SALE, REGISTER_EXPENSE, REGISTER_PRODUCT, REGISTER_PRODUCT_WITH_STOCK, REGISTER_PRODUCTS_BATCH, UPDATE_PRODUCT_PRICE, ADD_STOCK, CANCEL_SALE, CANCEL_EXPENSE, CANCEL_STOCK, CANCEL_LAST_OPERATION, DEACTIVATE_PRODUCT.
- Reads: current stock, revenue, profit, sales summary (`services/analytics_service.py`, `services/stock_service.py`), plus the 8 command-center module snapshots: caja (Resultado), productos, stock, ventas, costos, produccion, logistica, proveedores. Costos/Produccion/Logistica/Proveedores are READ-ONLY in the command center today; the chat is currently the only write path for several domains.

### The command-center surface
- FastAPI + Jinja2. Module registry: `backend/modules/registry.py` (8 modules), each exposing one `snapshot(phone) -> ModuleSnapshot` (`backend/modules/protocol.py`). Home fan-out: `backend/modules/home_service.py`. Attention aggregation: `backend/modules/attention_service.py`.
- LIVE at https://beans-command-center.mdlautomations.duckdns.org (uvicorn, cluster 212.56.44.209, login-gated). Also tenants.mdlautomations.duckdns.org.

### The chat seam (stays)
- Widget: `backend/static/js/chat_widget.js` (`window.beansChat`), POSTs `{message}` to `/api/tenants/{phone}/chat`, consumes `{response, metadata}`. Greeting: GET `/api/tenants/{phone}/chat/greeting`. Slot: `backend/templates/_timonel_slot.html` included once in `backend/templates/cc_base.html`.
- Route: `backend/api/chat_tenant.py` (`chat_with_tenant`), mounted under `/api/tenants` with `Depends(require_tenant_match)`.

### Single business, no test tenant
- Single-business "phone-less" pivot (PRs #166/#167) is BRANCH-ONLY, not on master. It rewrites page URLs via middleware but the chat endpoint stays `/api/tenants/{phone}/chat`; phone injected server-side from the session cookie.
- "The business" = one tenant row keyed by fixed phone `+5491100000001`, business_name Beans&Co (`configs/tenant_registry.json`). No test tenant exists.
- Auth: Google OAuth -> signed session cookie `beansco_session` carrying `{kind, user_id, email, phone_number, role}`. `require_tenant_match` (`backend/auth/dependencies.py`) already resolves the business from the session. The URL `{phone}` is redundant with the session. A single-business chat SHOULD resolve the business from the session and can drop the phone from the chat URL. Design default to confirm in panel.
- DB: dual-mode (SQLite file-per-tenant / Postgres schema-per-tenant), selected by `USE_POSTGRES`. Prod is Postgres, schema-per-tenant via `tenant_context(phone)`. Raw SQL, no ORM. Models in `backend/models/schemas.py`. Tables per tenant: products, sales, sale_items, expenses, stock_movements, + views revenue_paid, profit_summary, sales_summary, stock_current.

### The engine to reuse (the warm gateway)
- `deploy/gateway.mjs` (server, source of truth) -> `deploy/beans-ai.nomad.tmpl.hcl` + `deploy/build-hcl.mjs` -> `deploy/beans-ai.nomad.hcl` (generated). Tests `deploy/gateway.test.mjs`.
- Provides POST `/run` (bearer-gated, constant-time compare; body `{system, prompt, json_schema?, max_tokens?}`) and GET `/health`. Warm child pool (`ChildPool`, target 2): pre-spawned `claude -p --input-format stream-json --output-format stream-json --max-turns 1`, one turn per child, disposed after (warmth + zero cross-turn history), one-shot fallback.
- TODAY it disallows ALL tools and omits `--dangerously-skip-permissions`. For native tool-use this changes: our narrow MCP tools enabled (built-ins still disallowed), `--max-turns` > 1, and the child lifecycle moves to one child per user REQUEST (full tool loop) then disposed, preserving cross-tenant isolation.
- NOT deployed. Held pending Dario minting a dedicated `claude setup-token` (tracked eldaroo/beans-assistant#157/#158). Must use a DEDICATED beans token, never the shared Quinn/Wal token. Isolation: secret allowlist = token + bearer only; entrypoint greps env for org-keyring shapes and fails closed; box holds no DB.

## What Quinn knows about the project state

- This repo already carries specs 001-005. Spec 005 (Gemini->gateway backend swap of the OLD Timonel) is superseded by this spec's intent: the old multi-agent brain itself is retired, not just re-pointed.
- `/develop --headless` will drain this spec's children in one continuous run (strict-local, deploy to prod on beans-command-center as the closing act). Quinn has full access and deploys end to end; the one genuine external gate is Dario minting the dedicated subscription token.

## The six review questions (same for every panelist)

1. What problem is this actually solving?
2. What is the smallest first version that proves the idea?
3. What 3 risks would kill this if ignored?
4. What does success look like at 90 days?
5. What atomic tasks does this break into? (list 5-15, each <= 1 day of work)
6. What is the one thing only your faculty would have noticed?
