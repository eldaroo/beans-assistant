# Context packet: Beans&Co Production and Landed-Cost Engine

Run id: production-landed-cost-engine-20261013-093842
Target repo: eldaroo/beans-assistant (local: clients/eldaroo/beans-assistant)
Default branch: master. Base: origin/master @ 7fc545e. Spec branch: spec/production-landed-cost-engine.
target_kind: existing. Next spec ordinal: 003. architecture_author: true, mode: update, next decision ordinal: D-013.
kaze_attach: true (user-facing). Sacred check (Section F): true (external WhatsApp send to third parties plus supplier personal data plus multi-user access).

Each panelist writes against THIS packet, in their own voice, in their own review file. Do not coordinate; the synthesis is Quinn's job.

---

## The raw idea (verbatim, from the CEO of Beans&Co, voice transcript, Spanish)

Beans&Co makes coffee bracelets ("pulseras de café"). The CEO (a friend of Dario) described, by domain, what the platform should hold. Transcript, lightly cleaned:

> Vamos a comenzar por producción. Hay que decir cuántas pulseras se van a producir por semana o cada cinco o seis días. Cada cuánto llegan al lugar de donde se van a enviar, que es el principal, el de María en Armenia. Qué se necesita para la compra de esas pulseras y con quién se habla: con cada proveedor de pulseras, que en este caso es María, que trabaja con otra gente, y Víctor, que trabaja por su cuenta.
>
> También el tema de proveedores de quién nos provee café, quién lo tuesta. Costos de los mismos, de toda la producción: costo de mano de obra, costo de las maderitas que usamos, costo de hilo, costo del café tostado. Luego la durabilidad de las pulseras, que también tiene que ver con producción; estamos intentando hacerlas más resistentes.
>
> Algo muy importante: qué podemos hacer para que María y Víctor y cada uno de los proveedores constantemente nos estén informando de cómo viene todo, con un WhatsApp automatizado cada tanto. Después, tener una lista con los proveedores: quién nos da el café, quién las piedras, quién nos da las cosas para hacer los aros, las argollas, las piedras, etcétera.
>
> De producción sale el tema de envíos, que en principio estamos enviando desde DHL Armenia, y hay otro lugar que se llama Mis Envíos Express en Pereira. Habría que averiguar y tener exactos los costos de envío y también los costos de aduana de importación cuando entran.
>
> Por otro lado, en la producción están los packaging: tener en cuenta el costo de cada packaging y dónde salir a buscarlos en Pereira. Y también tenemos la producción de exhibidores; hoy estamos en Costa Rica, tenemos que ver cuánto sale y dónde vamos a producir, en Armenia o en Colombia.
>
> En forma, tenemos que llegar al costo final por pulsera en cada lugar: cuánto sale la pulsera en Colombia, cuánto en Armenia, cuánto en Costa Rica, teniendo en cuenta los costos de los exhibidores y de todo, que son costos indirectos. Tener en cuenta todos los costos indirectos.

## Confirmed discovery (Quinn asked, CEO answered)

- **Who loads data.** Multi-user on the site. María (bracelet supplier, works with a team) and Víctor (independent supplier) can load their own production and data directly. The CEO loads too. Open to adding more suppliers as users.
- **Currency.** Everything in USD. Inputs are paid in Colombian pesos (COP) and some in Costa Rican colones (CRC); normalize to USD on entry.
- **Objective.** Both uses are in scope: (1) set the sale price, and (2) compare where to produce and ship, by country.
- **Product types.** Several bracelet types and variants exist. The CEO will send the inventory later. Do not block on it; model costing per type/SKU and let inventory load as data.
- **Where it lives.** Same Google-OAuth login and same Postgres base as the existing Beans platform. Production and costing becomes the PRIMARY surface. The prior WhatsApp sales/stock assistant is reframed, not deleted: sales, stock, and expenses stay as secondary sections, no code torn out. (Dario confirmed via AskUserQuestion: "Reencuadrar, no borrar.")

## The core job in one sentence

Answer, for any bracelet type: what does one bracelet truly cost, landed, in each country (Colombia, Armenia-Colombia, Costa Rica), all-in, with indirect costs prorated, expressed in USD. Everything else in the platform feeds that number.

---

## The existing system (ground your review here; read the real source before prescribing)

Repo is a Python FastAPI + Jinja server-rendered app (NOT React). LangGraph assistant ("Timonel") plus a WhatsApp Baileys connector. Deploys to a Nomad cluster. Primary channel today is the web platform ("Bitácora AI") behind Google OAuth; WhatsApp is secondary.

Multi-tenant, SCHEMA-PER-TENANT Postgres. Per-tenant tables already defined in `database_pg.py` `create_tenant_schema`:

- `products` (id, name, SKU, unit_price, ...)
- `sales`, `sale_items`
- `stock_movements`
- `expenses`

Backend layout (`backend/`):

- `api/`: auth, analytics, chat, chat_tenant, expenses, onboarding, onboarding_web, products, sales, stock, tenant_scope, tenants
- `repositories/`: analytics, app_users, expenses, pending_onboarding, products, sales, stock, tenants  (note: `app_users_repository.py` already exists, so there is some user model to build the supplier-role on)
- `services/`: analytics, auth, chat, expenses, onboarding_*, products, sales, stock, tenants
- `auth/dependencies.py`: auth guards (`require_tenant_match` pattern; 401/403 redirect handled app-level per prior spec)
- `models/schemas.py`
- `templates/`: base.html, login.html, onboarding.html, tenant_detail.html (the dashboard), tenants.html

Timonel pipeline (`agents/`, `graph.py`): decomposer, router, expander, resolver, write_agent, field_labels, pending; LangGraph wiring in `graph.py`. The WhatsApp connector is `whatsapp_baileys/` with a scan/link page; sessions are single-link like WhatsApp Web.

`ARCHITECTURE.md` at repo root is the Timonel decision log, D-001 through D-012. It is strictly about interpretation and orchestration. The costing engine is a NEW domain and will append decisions from D-013; do not disturb D-001 through D-012.

Prior specs on disk: `specs/001-timonel-conversational-memory`, `specs/001-timonel-flexible-interpretation`, `specs/002-timonel-pending-operations`.

---

## The shape of the costing problem (the hard part, for Marcus especially)

A landed cost per bracelet type, per country, decomposes into:

1. **Direct materials (bill of materials per type):** coffee (green), roasting, wood pieces ("maderitas"), thread ("hilo"), stones/beads, rings/clasps ("argollas/aros"). Each is an input with a supplier, a purchase currency, and a cost per unit of input; the BOM maps input quantities to one bracelet.
2. **Direct labor:** paid per bracelet or per batch (María's team, Víctor).
3. **Packaging:** per-unit packaging cost (sourced in Pereira).
4. **Outbound logistics:** shipping (DHL Armenia; Mis Envíos Express in Pereira) and import/customs duty on arrival into the destination country. Some of these numbers are UNKNOWN today and must be modelable as PENDING.
5. **Indirect costs prorated per unit:** display stands ("exhibidores", today produced in Costa Rica, maybe moved to Colombia), and any other overhead. The allocation method (per unit produced over a period, per revenue, per batch) is a load-bearing decision and is unresolved. Name the method you recommend and why.

Multi-currency: inputs in COP/CRC, some logistics in USD. The normalization-to-USD decision (store original currency plus an FX rate plus the USD amount for an audit trail, versus store USD only; where the rate comes from and how often it updates) is unresolved. Name your recommendation.

Completeness: because some costs are genuinely unknown ("habría que averiguar"), the landed cost must render as a number with a completeness state (which cost components are filled, which are PENDING), never a false-precise total that hides a missing shipping or customs line. The platform should surface the gaps and prompt to fill them.

## Tensions worth naming (do not resolve them for me; argue your side)

- **Supplier-as-user access scope.** María and Víctor log in and enter their own production and input costs, but should they see the full landed-cost model, the sale price, other suppliers' costs? A supplier seeing another supplier's prices, or the CEO's margins, is a consent and competitive-harm surface. Where is the line?
- **Automated WhatsApp check-ins to third parties.** Sending scheduled WhatsApp messages to María, Víctor, and input suppliers asking "how is it going" and parsing replies into production/stock updates is an external send on behalf of the business to real people. Consent to be messaged, cadence that is not harassment, truthful identification of the sender, and what happens to a free-text reply that does not parse, are all live. This is why Mar'ah (Legion Action Gate) and Edut are on the panel.
- **How much is M1.** The arc is large: BOM and input-cost model, supplier directory, production tracking, multi-currency normalization, logistics and customs, packaging, display-stand indirect allocation, the landed-cost computation per country, the multi-user supplier role, the automated check-ins, and the UI reframe to make costing the primary surface. Name the smallest first version that proves the core (a credible landed cost for one type in one country) and sequence the rest honestly into milestone cohorts of at most 10 children each. No upper cap on total tasks; the spec is the whole problem.
- **Reuse versus new.** The WhatsApp check-in should reuse the existing Baileys connector and Timonel pipeline, not a second channel. The costing data model is new per-tenant tables. The UI reframe reorders existing nav around a new home. Say what you would reuse and what you would build.

## Operational facts for the build (not for debate, for grounding)

- Repo pushes as the `eldaroo` gh account (it flips back to autod3v between commands; re-assert).
- The local dev machine disk is at 2GB free; heavy builds and `npm install` will struggle until space is freed. Spec authoring (markdown plus a small mockup) is fine.
- The platform is operated in Spanish by the CEO and suppliers; copy is Spanish. The spec and all artifacts are English per the voice rule, Spanish only inside quotes.

## REFRAME (Dario, mid-run, 2026-10-13) — read this, it moves the center of gravity

After the first panel and the costing mockup, Dario reframed the spec. The target is no longer a landed-cost engine. It is the **Beans Control Center**: the single platform that nucleates everything important about running Beans, a command center the CEO opens to run the business. Landed cost stays, but as ONE module, not the whole thing.

Two decisions Dario made (binding):

1. **The nucleus is a status panel plus an attention strip.** When the CEO opens the control center, the first thing he sees is the state of the business at a glance (production this week, stock, cash, margin) with a strip on top of "what needs your attention today" (low coffee stock, a pending customs line, an overdue supplier check-in), and drill-down into each module. Classic command center, not a to-do list and not raw numbers buried.

2. **Costing numbers live in the platform; scenario exploration lives in the chat.** The platform stores and always shows cost and margin per country (auditable, multi-user). The exploratory "what if I move display-stand production to Colombia" is handled by talking to the assistant (Timonel), which reads those stored numbers and recomputes. So the costing module is light: it owns and displays the facts; the heavy scenario UI is out, the conversation carries it.

The module map (the CEO's own domains plus what already exists, now all first-class):

- **Home / Panel** — status tiles plus the attention strip, the nucleus.
- **Producción** — units per week, arrival cadence, durability.
- **Proveedores** — directory (coffee, roasting, stones, María, Víctor) plus status plus check-ins.
- **Costos y margen** — landed cost per country, numbers in the platform, scenarios via the assistant.
- **Inventario / Stock**, **Ventas**, **Caja / Gastos** — the existing Beans surfaces, promoted from secondary to first-class home modules, not torn out.
- **Logística** — shipping and customs.
- **Asistente (Timonel)** — the conversational layer over all of the above, including costing scenarios.

What survives from the first panel unchanged: the costing data model and FX decisions (D-013 to D-016), the supplier membership model and within-tenant scope (D-017), the Baileys/Timonel check-in reuse and its sacred gate (D-018), and all of Edut's and Mar'ah's consent findings. What changes: the top-level frame is now a command-center shell with pluggable modules; the UI reframe (D-019) becomes "nucleate the existing surfaces as first-class modules under a status home", not merely "reorder the nav"; and a new conversational-scenario read-path is added for costing.

The re-deliberation panelists address the NEW top-level shape: the command-center home (status plus attention engine), the module framework and how every module plugs into it, the attention-signal set, the assistant-reads-the-numbers scenario layer, and the re-sequencing of the whole arc so the shell and the home land before module depth.

## Voice rule (applies to your review)

No em-dashes, no en-dashes, no hype words, no TL;DR, no emojis, no exclamation marks. Plain English. Spanish only inside attributed quotes.
