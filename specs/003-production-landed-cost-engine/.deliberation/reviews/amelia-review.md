# Amelia review: Production and Landed-Cost Engine

I read the real source before writing this. Notes below cite files.

## 1. What problem is this actually solving?

One number: what does one bracelet truly cost, landed, in each country, in USD, with the unknowns shown as unknown. Today `products.unit_cost_cents` is a single flat integer a human guesses. There is no bill of materials, no supplier directory, no multi-currency, no logistics or customs line, no indirect allocation. The business cannot price or compare production sites because the cost is a guess, not a computed, auditable figure with a completeness state.

## 2. What is the smallest first version that proves the idea?

One bracelet type, one country, computed and rendered. Direct materials from a BOM plus direct labor plus packaging, summed in USD cents, shown with a completeness badge that names which lines are PENDING (shipping and customs allowed to be empty). No supplier login, no WhatsApp, no cross-country compare yet. Data entered by the CEO through one Jinja form. If a credible landed cost renders for the "pulsera clásica" in Colombia with two lines marked PENDING, the idea is proven and every later cohort is additive.

## 3. Three risks that would kill this

Risk one, the auth model. See question 6. This is the first thing to fix or suppliers cannot exist.

Risk two, schema-per-tenant migration. There is no Alembic. `create_tenant_schema` in `database_pg.py` builds tables imperatively with `CREATE TABLE IF NOT EXISTS`. New costing tables land for new tenants only unless a forward migration loops every row of `public.tenants` and applies the DDL to each schema. Reuse the per-row SAVEPOINT discipline already proven in `register_products_batch` so one bad schema does not abort the whole migration.

Risk three, money. Every amount is `*_cents INTEGER` and `revenue_paid` / `profit_summary` views sum raw cents with no FX. `register_expense` stores a `currency` column but downstream sums it blind, so a COP amount silently corrupts profit. The landed-cost engine must resolve FX to USD cents at write time and store original amount, rate, and USD cents for the audit trail. Do not trust the existing `currency` column as if it converts anything. It does not.

## 4. What does success look like at 90 days?

The CEO opens the platform, costing is the home surface, and for every bracelet type she sees a landed cost per country in USD with an honest completeness state. María and Víctor log in and enter their own production and input costs without seeing each other's prices or the CEO's margin. Automated WhatsApp check-ins run on a cadence and parse replies into production updates through the existing Timonel pipeline. Sales, stock, and expenses still work, untouched.

## 5. Atomic tasks

1. Add `public.tenant_memberships(user_id, tenant_phone, role, scope)` plus a cross-schema-safe migration; new `backend/repositories/memberships_repository.py`.
2. Rewrite `require_tenant_match` in `backend/auth/dependencies.py` to consult membership, not phone equality; add `require_supplier_or_owner`.
3. Add costing tables to `create_tenant_schema` in `database_pg.py`: `inputs`, `suppliers`, `bom_lines`, `production_batches`, `logistics_costs`, `indirect_costs`.
4. Write the forward migration that loops `public.tenants` and applies the new DDL per schema with the `register_products_batch` SAVEPOINT pattern.
5. New `backend/repositories/suppliers_repository.py` and `bom_repository.py`.
6. New `backend/services/costing_service.py` with `landed_cost(type, country)` returning amount plus completeness state.
7. FX helper: store original amount, rate, and USD cents; add columns and a resolve-on-entry path.
8. New `backend/api/costing.py` routes behind the supplier-aware guard.
9. Costing home partial and nav reorder in `backend/templates/tenant_detail.html` (Jinja plus Alpine, no React).
10. Supplier-to-tenant inbound routing plus a check-in scheduler in `whatsapp_baileys/server.js`, reusing the `/api/tenants/{phone}/chat` Timonel path.
11. Tests for costing_service, the guard, and the migration against two seeded schemas.

## 6. The one thing only my faculty noticed

A tenant is keyed by phone. `phone_to_schema_name(phone)` makes the phone the schema, and `require_tenant_match` in `backend/auth/dependencies.py` grants access only when `user.phone_number == phone`. A supplier is a different person with a different phone, so `AppUsersRepository.get_by_email` returns María's row carrying her phone, and the guard returns 403 for every tenant route unless her role is admin. There is no user-to-tenant membership anywhere. You cannot graft a supplier role onto this; you must first break the one-user-equals-one-phone-equals-one-tenant assumption with a membership table, then the role work is small. Build task 1 and 2 before anything else, or the whole multi-user premise sits on a guard that will reject it.
