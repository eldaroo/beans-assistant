# Beans Control Center — Rebrand Design System

Clean light SaaS. One vivid accent. Air over ornament. Built directly from these tokens.

## 1. Palette (all pairs WCAG AA)

Light:
- Background `#F6F7F9`
- Surface / card `#FFFFFF`
- Border subtle `#E4E7EC`
- Text primary `#101828`
- Text muted `#667085`
- Accent `#4F46E5` (indigo). Hover `#4338CA`. Soft tint `#EEF0FE`. Accent text on accent fill `#FFFFFF`.
- Good `#067647` (text/icon), fill `#ECFDF3`
- Warn `#B54708` (text/icon), fill `#FFFAEB`
- Danger `#B42318` (text/icon), fill `#FEF3F2`

Dark (a different time of day, not an inversion):
- Background `#0C0E12`
- Surface / card `#16181D`
- Border subtle `#2A2E37`
- Text primary `#E6E8EC`
- Text muted `#98A2B3`
- Accent `#818CF8`. Hover `#A5B0FC`. Soft tint `#1E2033`.
- Good `#47C97E`, fill `#0F2A1D`
- Warn `#E0A458`, fill `#2E2514`
- Danger `#F08C84`, fill `#2E1816`

## 2. Typography

Family: **Inter** (Google Fonts) for all UI. **JetBrains Mono** only for money and cost numbers.
- Page title 28px / 700
- Tile number 32px / 650, mono, tabular-nums
- Tile label 13px / 500, muted, letter-spacing 0.02em
- Body 15px / 400, line-height 1.55
- Caption 12px / 500, muted

Mono carries every USD-cents value and the landed-cost total so figures align column-wise and read as fact.

## 3. Elevation and shape

- Radius: cards 12px, tiles 12px, chips/badges 8px, buttons 10px, inputs 10px.
- Card shadow: `0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)`.
- Attention strip shadow: `0 2px 8px rgba(16,24,40,0.08)` so it sits one layer above the scorecard.
- Dark mode drops shadow and gains a 1px `#2A2E37` border instead.
- Rule: a surface earns shadow only when it floats above siblings (strip, menu, modal). Flat scorecard tiles use a 1px border, no shadow, until hover.

## 4. Spacing and density

- Base unit 4px. Scale 4/8/12/16/24/32/48.
- Tile padding 24px. Grid gap 16px. Page gutter 32px desktop, 16px mobile.
- Scorecard: 3 columns at 24px between tiles, max content width 1120px centered. The home breathes through generous gutters and a 32px gap between the attention strip and the scorecard, not through empty filler.

## 5. Component treatments

- **Status tile:** label top (muted caps-light), number below in mono, trend on its own line as a small arrow glyph plus signed value in the semantic color. Number is the loudest thing on the tile.
- **Attention strip:** three rows, severity ordered. Each row leads with a shape icon, not color alone: danger = filled triangle, warn = filled circle, info = outline circle. Color reinforces, never carries. Left 3px accent-or-semantic rail on each row.
- **Completeness badge:** pill, fill = warn tint, text `Parcial · 4 de 6`, dotted lower border under the total it qualifies.
- **Pending chip:** `Pendiente` in muted text on a hatched 8px chip; it holds its slot in the component column and never collapses, so the gap is visible.
- **Total refusing false precision:** when any component is pending, the total shows `USD 12.40 +` with the `+` in muted mono and a caption `Faltan 2 componentes`. No invented zero.
- **Primary button:** accent fill, white text, 10px radius, 40px tall, hover to `#4338CA` with 1px lift. Height never below 44px tap target on mobile.
- **Nav:** left rail 240px, active item = accent soft-tint background with accent text, 2px accent left marker.

## 6. Motion grammar

- Entrance: tiles fade and rise 8px, 320ms `cubic-bezier(0.16,1,0.3,1)`, staggered 40ms.
- Hover: tile border to `#D0D5DD`, shadow to card recipe, 140ms ease-out.
- Attention rows: 200ms ease-out on mount.
- Reduced motion: opacity only, no translate, 120ms; stagger removed.

## 7. The one move

The scorecard is built on a strict mono-aligned numeric grid, and every figure that cannot be fully known wears its pending state in the open rather than rounding to a confident number. The interface is calm because it is honest: a total that says `USD 12.40 +` with two components visibly waiting reads as a system that knows what it does not know, which is what separates a trustworthy control center from a generic admin template.
