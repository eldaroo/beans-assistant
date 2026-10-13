# Sally UX design notes: Production and Landed-Cost Engine

## Navigation order and what reads first

Primary nav, top to bottom: **Costo por pulsera** (default landing), then a secondary group labeled **Operacion** holding **Ventas**, **Stock**, **Gastos**. Nothing is removed; the three move down one level into a labeled group, still one tap away.

On the costing home the first thing that reads is one line: the bracelet type and country selectors, then the single USD total with its completeness badge directly under it. The component column reads second. The user sees the answer, then how it was built. Hierarchy order: total plus badge, selectors, component lines, primary CTA.

## Hierarchy

The total is the largest type on the screen. The badge sits beside it: `Parcial - 4 de 6` or `Completo`. Each component line is one row: label on the left (materiales, mano de obra, packaging, envio, aduana, indirectos), value or chip on the right. A missing line never reads as zero; it reads as the word **Pendiente**.

## Affordances: chip vs link vs button

- A pending line shows a **Pendiente chip** (neutral, not red; pending is not an error). The chip is the trigger: the whole row is tappable and opens the fill form for that line. The chip carries an aria-label `Completar envio`.
- The screen has exactly one **primary button**, `Completar linea pendiente`, which jumps to the first pending line. One button, one strong action.
- Filled values are plain text, not links, so the eye separates known from unknown.
- Country compare selection is a **segmented control** of three labels (Colombia, Armenia-Colombia, Costa Rica), not a dropdown, so all three stay visible. The lowest complete total is marked with a quiet `Mas bajo` tag, never color alone.

## Mobile 375 to desktop 1280

At 375 the costing home is one column: total and badge pinned at top, component rows stacked full width, the primary button fixed above the thumb zone. Country compare at 375 stacks the three cards vertically, each with its own badge. At 1280 the component column sits left, a summary rail sits right, and country compare lays the three cards side by side. Supplier surface at 375 is a single column of the supplier's own rows; at 1280 it gains a left label column. Reflow is layout only; no content appears or disappears across widths.

## Focus order, keyboard parity, touch targets

Tab order follows visual order: type selector, country selector, each component row top to bottom, then the primary button. Enter or Space on a focused row opens its fill form. Escape closes it and returns focus to the row. Every row, chip, button, and segmented option is a real focusable control with a visible focus ring. All touch targets are at least 44 by 44 pixels, rows included.

## Empty and error states, concretely

- **Empty:** heading `Todavia no hay costos cargados`, one line `Carga el primer insumo para calcular el costo de una pulsera`, and one primary button `Cargar primer insumo`. No empty table.
- **Loading:** skeleton rows matching the six component lines.
- **500:** `No pudimos calcular el costo ahora. Intenta de nuevo en unos minutos` with a `Reintentar` button.
- **Validation 4xx:** inline under the field, `Revisa el monto: debe ser mayor a cero`, valid input preserved.
- **403:** `No tienes permiso para ver este costo` plus a next step `Volver a tus datos`.

## Anti-patterns to avoid

- Do not thin, merge, or restyle the existing Ventas, Stock, or Gastos surfaces. The reframe only reorders nav.
- Do not hide margins behind a conditional on a shared screen. Margins never render on any supplier view by any code path.
- The supplier surface is a **separate route** (its own room), showing only Maria's or Victor's own inputs and production as a read-and-correct view, never margins and never another supplier.
