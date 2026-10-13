# Bob reframe review: Beans Control Center

## 1. What problem is this solving?

Beans has no command center. The CEO wants one screen: the business at a glance, an attention strip for today, drill-down per module, costing among them.

## 2. Smallest first version that proves the idea

The shell and home over the sales, stock, and expenses tables that exist: tiles and an attention strip, no new data model. The old one-landed-cost slice now proves the second module, not the first.

## 3. Three risks that would kill this

- Costing as M1 again: the home is built twice, the frame stays unproven.
- A framework modules ignore: no shared registry or attention contract, so the home goes bespoke.
- Supplier login or WhatsApp pulled forward: they look independent, but they carry human gates.

## 4. Success at 90 days

The CEO opens the center, sees stock, cash, sales, and margin with a live strip, and runs scenarios through Timonel. Proveedores, Producción, Logística are first-class. Supplier login and check-ins are shipped behind their gates or all that remains.

## 5. Atomic tasks, dependency-ordered into cohorts

Decision: the shell and home over EXISTING numbers land first. No new data model; it delivers Dario's nucleus and sets the contract later modules plug into. Costing is second because its tables are net-new. Order follows data: M2 tables precede M3 breadth and M4 indirect; M5's read-path needs M4's numbers; M6 and M7 come last behind gates.

**M1 shell and home over existing data**
1. Module registry and tiled home, tiles over existing sales, stock, expenses. AC: live tiles, low stock surfaces.
2. Three surfaces become modules, home default, Kaze pass. AC: nothing removed, reachable.

**M2 costing module (new tables)**
3. Costing tables and cross-schema forward loop. AC: present fresh and seeded, bad schema survives.
4. Input, BOM, multi-currency entry. AC: a COP line stores original, rate, USD.
5. Landed cost per type and country, completeness, tile. AC: fixtures return USD, missing line parcial.

**M3 production and cost breadth**
6. Producción module: units per week, cadence, durability. AC: production entered and shown.
7. All BOM input categories and packaging. AC: each enterable.
8. Labor completed-basis; logistics and customs PENDING. AC: a short batch raises per-unit labor.

**M4 multi-country, indirect, Logística**
9. Exhibidor indirect per unit per country per month. AC: zero-production month reads PENDING.
10. Compute three countries, compare and margin tile. AC: three totals, lowest complete marked.
11. Logística module and costing attention signal. AC: a pending customs line surfaces.

**M5 Proveedores and assistant read-path**
12. Proveedores directory, read-only, with status. AC: all suppliers listed.
13. Overdue check-in signal, data only. AC: overdue supplier surfaces, no send.
14. Timonel recomputes scenarios from stored numbers. AC: "mover exhibidores a Colombia" returns a recomputed cost.

**M6 supplier login (gated)**
15. tenant_members, supplier role scoped to own data, login consent, self-entry. AC: cannot read margin, price, or others; no login without consent; María within scope. (human: Andreas, Dario)

**M7 WhatsApp check-ins (gated)**
16. Messaging consent separate from login, cadence cap, opt-out. AC: names Beans&Co, states automated, honors opt-out. (human: Dario, Re'i)
17. Reuse Baileys and Timonel, no second channel. AC: existing pipeline only.
18. PRODUCTION_UPDATE parse with human fallback. AC: unparsable reply routes to the CEO. (human: Dario)

## 6. The one thing only my faculty would have noticed

The old trap was UI over a model that did not exist. Now the home stands on data that exists, so the frame ships first, costing behind it. The M1 registry and attention contract are load-bearing; every later module earns its tile by meeting them.
