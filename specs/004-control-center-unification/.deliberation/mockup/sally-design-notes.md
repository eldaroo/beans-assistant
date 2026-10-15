# Sally UX design notes — Control Center unification

UX, IA, affordances, accessibility. Kaze owns color. Notes in English; the copy they describe is Spanish.

## Navigation order and hierarchy

**Home reads top to bottom:** (1) attention strip, the one thing needing action today, so the owner acts before browsing; (2) Resultado tile, largest, numbers in mono, because money is why the owner opened the door; (3) the operational tiles in task frequency order: Productos, Stock, Ventas, Costos, then the lower-frequency Producción, Logística, Proveedores. One visual rank, not three columns of equals. If the attention strip is empty, it collapses to a calm one-line "Todo al día", never a blank band.

**Productos page reads:** (1) page title and the count ("12 productos activos"), so the owner knows scale instantly; (2) the primary action Agregar producto, top-right on desktop, full-width above the table on mobile; (3) the table. Title answers "where am I", count and Agregar answer "what can I do".

## Held nav rail, mobile vs desktop

Desktop 1280px: persistent left rail, active item marked by weight plus a left edge bar, not color alone. The rail never reloads; only the content slot swaps, with the 400ms page-enter Kaze specified. Mobile 375px: the rail collapses to a bottom bar of the four top tasks plus a "Más" sheet for the rest. Bottom placement keeps targets in the thumb zone. The active item is marked the same way. The rail stays put across every navigation, so the owner never feels a full-page bounce.

## Affordances

- **Agregar producto:** filled button, labeled verb, never an icon alone.
- **Editar / Eliminar per row:** on desktop, two visible text-plus-icon actions in the last column, always rendered, not hover-only, so keyboard and touch reach them without discovery. On mobile the row is tappable to open detail, with Editar and Eliminar inside. No swipe-to-delete as the only path.
- **Eliminar** opens a confirm dialog naming the product ("Eliminar Café Molido 500g") with the destructive button distinct; delete is soft-deactivate, so copy says "Se puede reactivar".
- **Modal:** close via an X top-right, Escape, and a Cancelar text button. No inline-edit in the table; edits happen in the modal to keep one validation surface.
- **Clarity cues:** chevron on the "Más" sheet and on expandable rows; X on the modal; focus ring on every interactive element identical in weight to hover, so keyboard users see what mouse users see.

## Keyboard and touch

Tab order follows visual order: nav, then Agregar, then table rows left to right, then modal fields top to bottom, then Cancelar, then Guardar. Enter and Space activate buttons; Escape closes the modal and returns focus to Agregar. Modal traps focus. Every touch target is at least 44px with 8px spacing.

## State UX

- **Empty:** illustration-light card, "Todavía no hay productos", and Agregar producto as the single next step.
- **Loading:** skeleton rows echoing the five columns, same height as real rows, so layout does not jump.
- **Error 500:** "No pudimos cargar los productos", a Reintentar button, rail stays usable.
- **Validation 4xx:** inline under the offending field, valid input preserved, Guardar stays disabled until fixed.
- **403:** "No tenés permiso para editar productos", read-only table, Agregar hidden not greyed.

## Anti-patterns to avoid

Hover-only row actions, color as the only state signal, full-page reload between tiles, placeholder used as label, icon-only destructive buttons, infinite scroll on a data table, and a confirm dialog with "OK".
