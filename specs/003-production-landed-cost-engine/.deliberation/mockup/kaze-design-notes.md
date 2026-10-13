# Kaze Design Notes — Costo por pulsera

## Atmosphere and density
Warm neutral paper, one accent, data in mono. This is a workshop ledger, not a dashboard. The CEO reads it the way a cook reads a recipe: ingredients first, sum last. Single column on 375, the components stacked as a vertical reasoning that falls toward its own total. Desktop 1280 widens the gutters and sets the comparison side by side; it never adds chrome. Density is low on purpose. Each component line owns a full row, breathes, carries one label and one value. Nothing floats.

## The spine: components sum down to the total
The six lines read top to bottom: materiales (via BOM), mano de obra, packaging, envío, aduana, indirectos. Each shows a USD value in mono, or a chip "Pendiente". The total sits at the end of its reasoning, not above it as a hero. A thin ledger rule separates the last component from the sum. "Costo final" is quiet, left aligned with its components, the number in mono beside it. Above it a badge: "Parcial · 4 de 6 componentes" or "Completo".

## The honesty treatment of the partial total
This is the law of the screen. A filled line settles. On populate it fades up and the value lands with weight, mono, full contrast, a 400ms ease-out that reads as something set down. A pending line does not settle. "Pendiente" is a soft chip, lower contrast, no mono number, held in a resting state that visibly waits. The eye can tell paid from owed without reading. When any line is pending the total refuses to pretend: the sum renders in a held, muted weight behind the "Parcial" badge, and the pending component names sit directly beside the number so no total is ever read alone. A partial country in the comparison carries this same doubt; it is never marked lowest, never allowed to win on an incomplete number. Only a "Completo" total earns full-contrast confidence and the lowest-complete marker.

## Motion grammar
Entrances stagger 60ms down the component column so the reasoning assembles in reading order. Ease-out, arriving and settling. The completeness badge counts up as lines fill: "3 de 6" to "4 de 6" is a small, earned beat. Loading is a skeleton that echoes the exact six rows, not a spinner, so the shape is promised before the numbers arrive. Under prefers-reduced-motion everything fades without travel, instant without jar. Dark mode is evening in the workshop: neutral-900 ground, off-white values, the accent desaturated so it glows rather than shouts.

## What earns its place, what I cut
Earned: the six labeled lines, the "Pendiente" chip, the completeness badge, the ledger rule, the comparison trio. Cut: the floating hero total, any gauge or progress ring, every icon that only decorates, the sales and stock surfaces pushed to secondary nav so costing is unmistakably home. The supplier surface is a separate room at a different temperature, calmer and smaller, showing only María's or Víctor's own inputs and production framed as "tu aporte". No margins, no prices, no peers. First names only.

## Felt verdict, four states
- Empty: an invitation. A new type with six waiting rows and a line that says begin, never a broken form.
- Loading: the six-row skeleton. The shape is kept while numbers arrive.
- Populated: at one line it is honest and sparse; at six it reads as a settled recipe; dense and all-filled it stays calm because the hierarchy holds.
- Error: the platform takes responsibility. 500, validation, and 403 each say what happened and the way forward, never accusing, never cryptic.

## The one move that makes the CEO exhale
The total that refuses to lie. When it reads "Parcial · 4 de 6" instead of a confident false number, the CEO stops guessing and trusts the screen.
