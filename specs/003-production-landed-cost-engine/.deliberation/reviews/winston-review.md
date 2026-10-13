# Winston review: Production and Landed-Cost Engine

Architecture-author seat. BuildOS.

## 1. What problem is this actually solving?

The business cannot answer what one bracelet truly costs, landed, in each country, in USD. So it prices by feel and sites production by feel. Every other feature exists to feed that one number. This is a costing-truth problem wearing a production-tracking coat.

## 2. What is the smallest first version that proves the idea?

One bracelet type, one country, direct costs only: a bill of materials over priced inputs, plus labor, plus packaging, each entered in its original currency and normalized to USD on entry. The landed cost renders as a USD number with a completeness state, shipping and customs shown as PENDING rather than folded into a false total. No supplier login, no WhatsApp check-ins, no indirect allocation yet. If that number is credible and the gaps read honestly, the core is proven and the rest is addition.

## 3. What 3 risks would kill this if ignored?

1. Treating supplier-as-user as a role flag. The tenant guard keys on phone_number, one user per tenant. Without a membership model and row-level scope, either suppliers cannot log in or a logged-in supplier reads the CEO's margins and a rival's prices. A consent breach and a competitive-harm breach at once.
2. A false-precise landed cost. If a missing shipping or customs line renders as a finished number, the CEO prices on a lie and never knows. Completeness state is load-bearing, not decoration.
3. Multi-currency with no audit trail. Store USD only and a disputed cost cannot be re-checked, a wrong FX rate is undiscoverable, and a later rate edit silently rewrites history.

## 4. What does success look like at 90 days?

The CEO has entered real costs for the actual inventory. Landed cost per type per country renders in USD with honest gaps. Maria and Victor log in, enter only their own production and input costs, and never see margins or each other's prices. Scheduled WhatsApp check-ins land production updates through Timonel, and an unparsable reply is kept, not dropped. Costing is the home surface. Sales, stock, and expenses still work, untouched.

## 5. What atomic tasks does this break into?

1. Costing migration: new per-tenant tables in `database_pg.py` `create_tenant_schema` (suppliers, cost_inputs, input_purchases, bom_lines, labor_costs, packaging_costs, shipping_lanes, customs_duties, indirect_costs, landed_cost_snapshots), with backfill for existing tenants. [autodev]
2. suppliers repository and api: `backend/repositories/suppliers_repository.py`, `backend/api/suppliers.py`. [autodev]
3. cost_inputs plus input_purchases repository and api, with original currency, fx_rate, usd amount, and a USD normalization helper. [autodev]
4. BOM repository and api keyed by product_id: `backend/repositories/bom_repository.py`. [autodev]
5. Landed-cost computation service producing a snapshot with completeness state: `backend/services/costing_service.py`. [autodev]
6. Indirect-cost allocation function (per unit produced, per country, per month) inside `costing_service.py`. [autodev]
7. Costing home template and route: `templates/costing.html`, `backend/api/costing.py`. [autodev]
8. Additive nav reorder in `templates/base.html` and `tenant_detail.html`, no deletion. [autodev]
9. tenant_members table plus membership-aware `require_tenant_match` in `backend/auth/dependencies.py`. [human: auth kernel]
10. Supplier role plus row-level data scope (own supplier_id only, margins owner-only). [human]
11. WhatsApp check-in scheduler: a periodic job calling the existing Baileys outbound in `whatsapp_baileys/`. [autodev after task 12]
12. Check-in reply parse reusing Timonel: new PRODUCTION_UPDATE intent plus verbatim capture of an unparsed reply. [human: external send, sacred gate]
13. Completeness-state rendering on the costing home. [autodev]

## 6. The one thing only my faculty would have noticed

The schema-per-tenant guard keys on phone_number, so the data model already assumes one human per tenant. Supplier-as-user is therefore not a role addition, it is a change to the membership model at the auth kernel. Reading `require_tenant_match` is the only way to see that the entire multi-user supplier story is blocked below the feature layer, and that the blocking task is not autodev work.
