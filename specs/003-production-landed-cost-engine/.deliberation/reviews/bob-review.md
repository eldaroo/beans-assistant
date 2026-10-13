# Bob review: Production and Landed-Cost Engine

## 1. What problem is this actually solving?

Beans&Co cannot answer one question: what does a single bracelet truly cost, landed, in each country, in USD, once indirect costs are prorated. Today that number lives in the CEO's head and in scattered WhatsApp threads. Without it, pricing and the produce-here-versus-there decision are guesses. Everything else in the packet feeds that one number.

## 2. Smallest first version that proves the idea

One bracelet type, one country, one currency path. The CEO enters a BOM for that type (materials plus labor), enters input costs in COP with an FX rate to USD, and the platform computes and shows a landed cost in USD with a completeness state that marks which lines are filled and which are PENDING. No suppliers-as-users, no WhatsApp automation, no multi-country compare, no reframed home. If that slice renders a credible, honest number for one type, the idea is proven. Breadth is sequencing after that, not a prerequisite for it.

## 3. Three risks that would kill this

- Building the UI reframe before the data model exists. Reordering nav around a costing home that has no tables behind it produces a demo, not a product. The model comes first; the reframe lands only once there is a real number to put on it.
- Wiring automated WhatsApp sends before the supplier role and consent are built. An external send to real third parties with no consent record, no sender identity, and no handling for an unparsable reply is a consent breach, not a feature. The channel waits for the role and the gate.
- Computing a landed cost before the BOM and input costs can be entered. A total built on empty inputs is false precision. Entry of BOM and costs must exist and be trustworthy before the compute is exposed.

## 4. What does success look like at 90 days?

The CEO prices every bracelet type from a real landed cost, in USD, per country, and trusts it because the completeness state shows nothing is silently missing. María and Víctor log in and enter their own production and input costs within their own scope. At least one automated check-in cadence runs with recorded consent and a clean path for replies that do not parse. Costing is the primary surface; sales, stock, and expenses remain reachable as secondary sections with no code torn out.

## 5. Atomic tasks, dependency-ordered into cohorts

**M1 costing-core vertical slice (prove one credible landed cost)**
1. Create per-tenant costing tables (input, bom, bom_line, cost_entry) in create_tenant_schema. AC: migration runs on a fresh tenant schema, tables present.
2. Add input and BOM repository plus service. AC: create and read an input and a BOM line for one type.
3. Add cost-entry model storing original currency, FX rate, USD amount. AC: a COP entry persists all three fields.
4. Implement landed-cost compute for one type, one country. AC: known inputs return the expected USD total in a unit test.
5. Add completeness state to the compute output. AC: a missing shipping line renders PENDING, not zero.
6. Add minimal costing screen: enter BOM and inputs, view the number and its gaps. AC: CEO completes the flow end to end for one type.

**M2 breadth of cost domain**
7. Model all BOM input categories (coffee, roasting, wood, thread, stones, rings). AC: each category enterable.
8. Add packaging per-unit cost. AC: packaging line appears in the total.
9. Add labor per-bracelet and per-batch. AC: both modes compute correctly.
10. Add logistics and customs lines as modelable PENDING. AC: unknown values hold without faking a total.

**M3 multi-country and indirect allocation**
11. Add display-stand (exhibidor) indirect cost input. AC: stored per period.
12. Implement indirect allocation method (recommend per-unit-produced-over-period). AC: per-unit indirect prorated into each total.
13. Extend compute to Colombia, Armenia-Colombia, Costa Rica. AC: three totals from one BOM.
14. Add FX source and refresh policy. AC: rate stamped on each entry, audit trail intact.
15. Add per-country compare view. AC: three landed costs shown side by side.

**M4 UI reframe (lands here, after the model and compute are real)**
16. Promote costing to primary home; demote sales, stock, expenses to secondary. AC: default route is costing, old sections reachable, no code removed.
17. Apply Kaze pass to the costing surface. AC: KAZE.md laws honored in review.

**M5 supplier self-service login (depends on data model, carries scope gate)**
18. Extend app_users with a supplier role. AC: a supplier user exists and authenticates via Google OAuth.
19. Scope supplier access to own production and inputs only. AC: a supplier cannot read another supplier's costs, the margin, or the sale price.
20. Supplier entry screens for production and input costs. AC: María enters her data within scope.

**M6 automated WhatsApp check-ins (depends on role plus consent gate, reuse Baileys and Timonel)**
21. Record per-contact consent to be messaged. AC: no send without a stored consent row.
22. Define cadence and sender identity in each message. AC: message names Beans&Co, cadence is bounded, not harassment.
23. Reuse Baileys connector plus Timonel pipeline for the check-in. AC: no second channel introduced.
24. Parse replies into production or stock updates with a fallback for unparsable text. AC: an unparseable reply routes to a human, never silently dropped.

## 6. The one thing only my faculty would have noticed

The packet names "how much is M1" as a tension, but the real sequencing trap is that three deliverables everyone wants early all depend on tables that do not exist yet. The supplier login, the WhatsApp automation, and the UI reframe each read as standalone features, and a team under pressure will start one of them first because they feel independent. They are not. All three sit on the costing data model. Pull any of them into M1 and you build a shell over nothing, then rework it. The honest order puts the model first and holds the attractive surface features until the thing they describe is actually real. That ordering is the whole contribution.
