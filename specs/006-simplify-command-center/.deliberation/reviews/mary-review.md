# Mary (Business Analyst) review — Simplify the Command Center

## 1. What problem is this actually solving?

Nine nav entries are not too many because nine is a large number. They are too many because each entry is a page the owner has to know exists, remember which one holds the answer, and navigate to before she can act. For one non-technical person running a real coffee-accessories business across three countries, the cost is not clicks, it is the standing question "where do I go to do this?" every single time. The real job to be done is: "tell me what needs my attention and let me handle it without me having to know how the software is organized." The rail exposes the system's internal module shape (Resultado, Stock, Costos, Proveedores). The owner does not think in modules. She thinks in tasks: did I get paid, is anything running out, is a shipment stuck. Timonel collapses the where question into a what question. That is the win.

## 2. Smallest first version that proves the idea

Two tabs. Tab one, "Hoy": the status tiles plus Timonel as the main column, not a corner widget. The owner reads the Atencion strip, then talks to Timonel to act (record a sale, log an expense, check stock). Tiles are drill-downs and confirmations, not the primary input. Tab two, "Negocio": the consolidated operational data (productos, stock, ventas, gastos) in one scrollable surface so she can see and hand-edit numbers when she does not want to talk. Keep costing, produccion, logistica, proveedores reachable from within those two surfaces, not as top-level tabs. Prove it by having the owner run one real day entirely from Tab one. If she can, the idea holds.

## 3. Three risks that would kill this

- Trust in AI writes to money. If Timonel records a wrong sale or expense and the owner cannot see and undo it instantly, she stops trusting it and goes back to spreadsheets. Every write needs a visible confirmation and a one-tap reversal.
- Discoverability collapse. Hiding eight modules behind chat means the owner no longer knows what the system can do. If she cannot discover capabilities, she underuses the product. The tiles must advertise what is possible.
- Loss of the audit surface. Costing and supplier check-ins are periodic review tasks, not conversational ones. Bury them too deep and they rot. They need a findable home even if not a top tab.

## 4. Success at 90 days

- The owner performs 80 percent or more of her weekly actions from the "Hoy" tab without opening a detail page.
- Median time from login to completing one action drops below 30 seconds.
- Fewer than 5 percent of Timonel writes are reversed by the owner (a proxy for trust).
- Weekly active use stays flat or rises after the cut (simplification did not cost capability).
- Zero support questions of the form "where do I find X."

## 5. Atomic tasks

1. Instrument current nav: log which modules the owner actually opens and how often.
2. Define the "Hoy" tab layout: tiles plus Timonel primary column.
3. Make Timonel the main column on "Hoy" (not corner slot).
4. Add visible write-confirmation and one-tap undo to every Timonel write.
5. Build the consolidated "Negocio" tab (productos, stock, ventas, gastos).
6. Make costing, produccion, logistica, proveedores reachable as drill-downs.
7. Add capability hints so the owner discovers what Timonel can do.
8. Reduce the registry-driven rail from nine entries to the chosen tabs.
9. Migrate the Atencion strip into the "Hoy" surface.
10. Run a one-real-day usability check with the owner, record friction.

## 6. The one thing only my faculty would notice

The nav mirrors the module registry, which mirrors the hidden schema-per-tenant kernel. The owner is being shown the engineering's data model as her menu. Simplifying the tabs is not a UI tidy-up, it is finally separating what the owner needs to do from how the system is built. That separation is the actual deliverable.
