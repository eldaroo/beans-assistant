# Simplifier review — Simplify the Command Center

## 1. What problem is this actually solving?

One non-technical owner runs one small real business and has to carry nine
places in her head to do it. Nine nav entries means nine mental models, nine
layouts, nine sets of buttons. She does not wake up thinking "I will open the
Logística module." She thinks "did the Costa Rica shipment clear" or "how much
did I make this week." The modules are built around the database schema, not
around her questions. The AI changes the economics: if she can ask the question
in plain words, the nine-door filing cabinet stops earning its cost. The job is
to run the business by asking, and to see trustworthy numbers when she wants to
look.

## 2. The smallest first version that proves the idea

Two tabs. That is the call.

- Tab 1, "Hoy": Timonel as the main column, not a corner widget. Full-width
  chat is the primary way to do and ask. Below or beside it, the existing home
  status tiles and the Atención strip stay as a glanceable panel. This one tab
  is where 90 percent of days end.
- Tab 2, "Negocio": one scrollable page, not four, holding Productos, Stock,
  Ventas, and Resultado (caja) as sections. This is the ledger she trusts and
  the place to fix what the AI got wrong.

Collapse map: Inicio folds into Hoy. Resultado, Productos, Stock, Ventas become
sections of Negocio. Costos, Producción, Logística, Proveedores get no tab at
all. They become "ask Timonel." Costos already has a read-only recompute path
in chat. Producción, Logística, Proveedores are low-frequency reference and
their signals (low stock, pending customs, overdue supplier) already surface in
the Atención strip on Hoy. Demote all four to conversation plus a drill-in link
the AI can open when needed. Do not build four more pages to hide them; let the
chat be the door.

## 3. Three risks that would kill this

- Over-cutting the ledger. Money must stay directly visible and directly
  editable without talking to anyone. Keep Resultado and Ventas as plain
  sections she can open and correct by hand. Hiding caja behind chat breaks
  trust the first time a number looks wrong.
- AI dead-ends. When Timonel cannot do a thing (bulk edit, a field it has no
  tool for), it must say so and hand her the exact section, not fail silently.
  A demoted module with no page and no working chat path is a hole.
- Blind writes to money. Every AI write that moves pesos needs a one-line
  confirm and an undo in the Negocio ledger. Trust is earned by letting her see
  and reverse, not by asking her to believe.

## 4. Success at 90 days

The owner holds two concepts, not nine. She opens Hoy, asks or glances, and only
opens Negocio to check or correct. She never asks where a feature lives, because
there are two places. Costos, Producción, Logística, Proveedores pages are gone
and unmissed.

## 5. Atomic tasks (cuts and merges)

1. Reduce the module registry nav to two entries: Hoy, Negocio.
2. Make Timonel the main column on Hoy; demote the corner widget.
3. Keep home tiles plus Atención as a panel on Hoy.
4. Merge Productos, Stock, Ventas, Resultado into one Negocio page as sections.
5. Remove Costos as a page; keep its chat recompute path.
6. Remove Producción, Logística, Proveedores pages.
7. Route the three removed signals into the Atención strip.
8. Add confirm-plus-undo to every money-moving AI write.
9. Add AI fallback: on an action it cannot do, link the Negocio section.
10. Delete dead routes, templates, and registry entries for removed modules.

## 6. The one thing only a simplifier would notice

The home page is secretly a second copy of all eight modules. Every module
already writes a snapshot() for the tiles. That snapshot is the real summary the
owner needs daily. So four of the eight modules exist twice: once as a full CRUD
page she rarely opens, once as a tile she reads every day. Keep the tile, delete
the page. The duplication is the cut.
