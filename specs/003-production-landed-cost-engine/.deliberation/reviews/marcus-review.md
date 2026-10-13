# Marcus review: Production and Landed-Cost Engine

## 1. What problem is this actually solving?

This is a unit-economics problem wearing a logistics costume. Beans&Co does not know the fully loaded cost of one bracelet, so every price it sets and every "where do we produce" decision is a guess dressed as a number. The job is a defensible landed cost per SKU per country: direct inputs plus labor plus packaging plus outbound freight plus duty plus a prorated slice of overhead, all in USD. Once that number exists and is trusted, pricing and location choices stop being opinions.

## 2. Smallest first version that proves the idea

One bracelet type, one country (Armenia-Colombia, since María and DHL Armenia are the known path), computed end to end. A BOM for that one type, input costs entered in COP with an FX rate and a derived USD value, direct labor per bracelet, packaging per unit, one shipping line, one duty line (both allowed to be PENDING), and one indirect allocation. Output: a single landed cost that shows its own completeness. No supplier portal, no WhatsApp, no multi-country compare. If this one number survives the CEO reading it against reality, the model is real.

## 3. Three risks that would kill this

1. Wrong indirect-allocation basis. Spreading exhibidor and overhead cost on a bad denominator produces a per-unit number that looks precise and is false, then drives a bad price or a bad "move to Colombia" call. Name the basis explicitly.
2. FX drift making stored USD stale. A USD figure captured at an old COP rate silently rots. A cost pulled three months later compares a fresh number against a stale one and the location decision tilts on currency noise, not on real cost.
3. False-precise totals hiding PENDING lines. A landed cost that reads "$3.80" while the customs line is unknown is a lie with a decimal point. The missing line must be visible, not buried in a sum.

## 4. Success at 90 days

The CEO, María, and Víctor enter real production and input costs. Every active bracelet type has a landed cost per country, each stamped with a completeness state. The CEO sets at least one sale price by reading the model instead of guessing, and has run one produce-here-versus-there comparison with the indirect costs included. No total is shown without its PENDING components named.

## 5. Atomic tasks (costing method explicit)

1. Per-tenant tables: `bom`, `input_costs`, `labor_rates`, `packaging_costs`, `logistics_lines`, `indirect_pool`, `landed_cost` with a completeness field.
2. BOM editor: map input quantities to one bracelet per type.
3. Input-cost entry with multi-currency rule (below).
4. Direct-labor capture, per bracelet or per batch, normalized to per unit.
5. Packaging per-unit entry.
6. Logistics and customs lines per country, each flagged filled or PENDING.
7. Indirect allocation engine (method below).
8. Landed-cost compute: `materials(BOM) + labor + packaging + shipping + duty + prorated_indirect`, per type per country.
9. Completeness model: each component is filled or PENDING; total renders with the gap list.
10. Per-country compare view.

Landed-cost formula: the sum in task 8. Indirect allocation: per unit produced over a trailing window (recommend a rolling period, overhead pool divided by units made in that window), because batches and revenue are both too lumpy and too gameable at this volume. Multi-currency rule: store original amount plus FX rate plus derived USD, rate captured at entry from one named daily source, never USD only, so the audit trail survives. Completeness: a landed cost always states filled versus PENDING.

## 6. The one thing only my faculty noticed

Direct labor paid "per batch" is a fixed cost masquerading as variable. If labor is a batch payment and the batch ships short, the real per-unit labor rises on the units that actually sold. The model must divide batch labor by units completed, not units planned, or every landed cost is understated on exactly the runs that went wrong.
