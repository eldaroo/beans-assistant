# Context packet — Simplify the Command Center (AI-first, 1 to 4 tabs)

Run id: simplify-command-center-20261017-141616
Target repo: clients/eldaroo/beans-assistant (existing). Issues host: eldaroo/beans-assistant.
target_kind: existing. architecture_author: true, mode=update (ARCHITECTURE.md exists, 411 lines).
Source: inline idea from Dario.

## Raw idea (verbatim, Spanish)

"fijemonos como podemos simplificar el command center, teniendo en cuenta q estamos instalando una AI para interactuar con todo. pensemos en entre un y 4 tabs como mucho para manejar todo"

Translation for panelists: simplify the Command Center. We are installing an AI (Timonel) to interact with everything. Target between 1 and 4 tabs at most to manage the whole business.

## What the product is today (ground truth, verified this session)

Beans Command Center is a single-business web app for Beans&Co (a small商 business: coffee bracelets / termos / accessories; produces and ships across Colombia, Argentina, Costa Rica). It is NOT multi-tenant from the owner's point of view any more. Stack: Python FastAPI + Jinja2 server-rendered pages + Alpine.js for per-page CRUD, Postgres (schema-per-tenant kernel underneath, hidden), deployed on a Nomad cluster. Live at https://beans-command-center.mdlautomations.duckdns.org. Owner logs in with Google and lands on /home.

Recent arc (this month): spec 003 built the Control Center (status home + costing), spec 004 unified it, then this session (a) made it single-business and phone-less, (b) rebranded to "Beans Command Center", (c) removed the legacy multi-tenant pages entirely, so there is now ONE surface: the Control Center.

### The current Control Center surface

A left rail (desktop) / stacked nav (mobile) with these entries, driven by a module registry (`backend/modules/registry.py`):

- Inicio (home): a status page. One tile per module + an "Atención" strip (low-stock alerts etc). Built by `home_service.build_home` which fans out one snapshot() per module concurrently.
- OPERACIÓN group, 8 modules, each its own page:
  1. Resultado (caja): ingresos, gastos, ganancia + gastos list + add/delete expense.
  2. Productos: catalog (SKU, cost, price, active) + add/edit/delete.
  3. Stock: on-hand per product + IN/OUT movements + low-stock.
  4. Ventas: sales list, status paid/pending, record-sale (line items), cancel, view-detail.
  5. Costos: per-product landed costing (inputs, labor, packaging, BOM, country), completeness ("USD x +").
  6. Producción: production records (units/week vs target, arrival cadence).
  7. Logística: shipping lanes, customs, pending-customs signal.
  8. Proveedores: suppliers + overdue check-in signal.

So the nav currently has 9 entries (Inicio + 8 modules). Each module is a full page with its own Alpine CRUD.

### Timonel (the AI) today

Timonel is an embedded chat assistant (bottom-right slot on every Control Center page, `_timonel_slot.html` + `chat_widget.js`). Backend: a LangGraph multi-agent system (router, resolver, read-agent, write-agent) wired at `/api/tenants/{phone}/chat`. It already can:
- WRITE operations: register sales, add/remove stock, create products, record expenses (natural language → DB writes).
- READ analytics: revenue, profit, stock, "qué pasa si" cost scenarios (read-only recompute).
- The brain runs on a Claude subscription gateway (spec 005) or Gemini fallback.

There is a chat-to-screen bridge (`cc_chat_bridge.js`, spec 004 cohort D) so that when Timonel acts on a domain, it can refresh or open that domain's page. Dario has signalled the chat/WhatsApp channel is secondary; the web app is the product.

So the AI is already capable of doing most CRUD by conversation. The idea is to lean INTO that: if the AI can do everything, the heavy per-module UI may not need to be the primary interface.

## The constraint Dario set

- Between 1 and 4 tabs MAXIMUM to manage the whole business.
- The AI (Timonel) is the thing being installed "to interact with everything" — treat it as a first-class, probably primary, way to operate.
- "Simplify" is the verb. The current 9-entry rail is what he wants cut down.

## What to deliberate (the 6 questions, answer all)

1. What problem is this actually solving? (Why is 9 modules too many for this owner? What is the real job to be done?)
2. What is the smallest first version that proves the idea? (A believable 1-4 tab shape + AI-first interaction that still lets the owner run the business.)
3. What 3 risks would kill this if ignored? (e.g., hiding power-user CRUD behind chat, trust in AI writes to money, discoverability.)
4. What does success look like at 90 days?
5. What atomic tasks does this break into? (5-15, each <= 1 day.)
6. The one thing only your faculty would notice.

## Design seed to react to (not a decision, a starting point for the panel)

One candidate shape the panel can accept, reshape, or reject: collapse the 8 operational modules into a small number of tabs organized by job, with the AI as the top-level operator.

- Possible tabs (pick 1 to 4): "Hoy" (the status home + the chat as the primary action surface), "Negocio" or "Operación" (one consolidated place for productos/stock/ventas/gastos), "Costos y producción" (the deeper costing/production/logística/proveedores), and maybe a fourth. OR fewer: one "Inicio con Timonel" tab where the chat drives everything and tiles drill in, plus one or two detail tabs.
- The AI is not a widget in the corner; it may be the main column. The tiles/pages become drill-downs and confirmations, not the primary input.

Panelists: react to this honestly. The owner is one non-technical person running a small real business. The win is "manage everything from one or a few places, mostly by talking to Timonel, with the numbers visible and trustworthy."

## Voice rule for all outputs

No em-dashes, no en-dashes, no hype words, no emojis, no exclamation marks. Plain English. Spanish only inside Dario quotes.
