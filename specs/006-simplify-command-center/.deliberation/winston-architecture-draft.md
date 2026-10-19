# Architecture-author addendum — Simplify the Command Center (AI-first tabs)

Mode: UPDATE. Scope: only the decisions impacted by collapsing nine nav entries into one to four AI-first tabs. Everything in D-001 through D-028 not named here is untouched. New decisions continue from the highest existing ordinal (D-028), so they begin at D-029.

### D-029: Tabs are a grouping attribute over the existing registry, not a new structure (refines D-020, D-023, D-026)

- **Chosen.** Add one field `group` to the `Module` descriptor (enum: `hoy`, `operacion`, `costos_produccion`). The rail renders each group as a tab; membership is data in `registry.py`. Three tabs in v1: Hoy (status home plus Timonel), Operación (productos, stock, ventas, caja), Costos y producción (costos, producción, logística, proveedores). Count lands at three, inside Dario's one-to-four bound.
- **Alternatives.** (a) A second tab-registry object mapping tab to a list of module ids. (b) Hard-code tab membership in `cc_base.html`. (c) One merged page per tab replacing the modules (see D-032).
- **Why this won.** The registry is already the single source of module truth. A grouping attribute keeps it so, and keeps adding or moving a module a one-field edit, never a template edit, preserving D-026 and Control Center AC1.
- **Why the alternatives lost.** (a) A second object duplicates identity and drifts from the registry. (b) Template hard-coding is the coupling D-020 forbids. (c) Merging is D-032's rejected path.
- **Implications.** The descriptor grows one field with a default, so an ungrouped module falls into Operación rather than vanishing. `href_for` and all routes are unchanged. Panel source: Winston.

### D-030: Timonel is promoted from the corner slot to a persistent primary column across all tabs (supersedes D-028's corner-widget placement clause dated 2026-10-14; keeps D-028's single-mount principle)

- **Chosen.** The chat widget still mounts exactly once through the slot in `cc_base.html` (D-028's single mount is kept). The slot becomes a persistent layout column on desktop and a dismissible sheet on mobile, not a bottom-right floating widget. On the Hoy tab the column is the primary action surface; on the other tabs it stays present as the operator.
- **Alternatives.** (a) Keep the corner widget. (b) A dedicated `/chat` tab only. (c) Duplicate the chat as a column per tab.
- **Why this won.** Dario is installing the AI to interact with everything. A corner widget signals secondary; a primary column signals primary. One mount still serves every tab, so the asset still loads once.
- **Why the alternatives lost.** (a) The corner contradicts the brief. (b) A chat-only tab splits the assistant off the surfaces it should assist, the exact reason D-028 rejected it. (c) Per-tab duplication drifts, violating D-028's one-mount rule.
- **Implications.** `cc_base.html` becomes a two-region shell: a Timonel column and the tab content region, collapsing to a single column plus chat sheet on mobile. The factory `window.beansChat` is unchanged; only its container and CSS change. Panel source: Winston, with Kaze on presence on every owner surface.

### D-031: The chat-to-content contract extends `beans:navigate` / `beans:refresh` with a tab dimension; it is not replaced

- **Chosen.** The `beans:navigate` payload gains `{tab, module}`. A small shell tab-router listens, switches tab if needed, then drills to the module panel or page. `beans:refresh` keeps its per-surface semantics from D-028: a chat action refreshes the content currently mounted and never claims to refresh a surface it cannot reach.
- **Alternatives.** (a) A new event bus. (b) A full page reload on every chat action. (c) A global refresh-all.
- **Why this won.** The bridge already exists (`cc_chat_bridge.js`). Adding a tab field is the minimal extension and preserves D-028's honesty rule about never claiming an unreachable refresh.
- **Why the alternatives lost.** (a) A new bus duplicates a working contract. (b) Reload loses Alpine state and fights the no-store model. (c) Refresh-all re-pays every snapshot, the regression D-027 guards.
- **Implications.** The shell owns a tiny tab-router mapping `{tab, module}` to the right content; when the target is not mounted it navigates the module route. Panel source: Winston, with Amelia on the contract extension.

### D-032: The eight per-module pages are kept as drill-downs behind tabs, not merged

- **Chosen.** Each module keeps its route, its `_build_view`, and its single Alpine factory (D-025). A tab is a container of its modules' surfaces, reached as tiles that drill in to the existing page, or by Timonel navigation. No mega-page, no combined factory.
- **Alternatives.** (a) Merge each tab's modules into one combined page and factory. (b) Delete the less-used modules.
- **Why this won.** The three-read-layer split (snapshot, `_build_view`, api) and the one-factory-per-page convention are what keep each surface cheap and independently testable. Merging re-couples them and discards proven CRUD. Simplifying the nav is a presentation goal, not a reason to rebuild domains.
- **Why the alternatives lost.** (a) A merged factory owns four domains' mutations at once, a fragile object that re-introduces the coupling D-020 removed. (b) Deleting modules loses function the owner still needs occasionally.
- **Implications.** Operación and Costos y producción each render their modules' headline tiles (reusing the provider snapshots) with drill-in to the existing page. Default: a tab shows its modules' tiles; the inline-primary-module variant is A-Q15. Panel source: Winston.

### D-033: Tabs reuse the existing snapshot fan-out; `home_service` groups by tab, no new data path

- **Chosen.** `home_service.build_home` still fans out one `snapshot()` per module concurrently, under the D-027 bound unchanged. The result is grouped by the registry `group` field into per-tab tile sets. Hoy shows the full status home plus the attention strip as today; Operación and Costos render the subset of tiles for their group. No new query, no new service.
- **Alternatives.** (a) A per-tab service that re-queries on tab switch. (b) Lazy per-tab snapshot fetch.
- **Why this won.** The fan-out is already concurrent and bounded. Grouping its output is free and keeps one data path and the 0.9s render.
- **Why the alternatives lost.** (a) Re-querying per tab multiplies load on the pool D-027 protects. (b) Lazy fetch adds a second path for no measured need at this module count.
- **Implications.** `build_home` returns grouped tiles, or the template groups by the `group` field at render; attention stays global on Hoy. If the #138 pool debt bites, it bites once at home load as today, never per tab switch. Panel source: Winston, grounded in D-027.

## Conventions

- Tab membership is the registry `group` field, never a template literal. A new module joins a tab by setting one field.
- Three tabs in v1: Hoy, Operación, Costos y producción. Labels Spanish. The count stays within one to four.
- The Hoy tab is the default landing; it is D-023's status home plus the Timonel column, so D-023's default-landing clause stands unchanged.
- Timonel mounts once (D-028 kept); the change is its container and CSS, not its factory.
- `beans:navigate` carries `{tab, module}`; `beans:refresh` stays per-surface and never claims an unreachable refresh.

## Non-goals

- No merging of module pages, no new or rewritten CRUD, no API change (D-032).
- No change to auth, multi-tenant scoping, channels, or the D-027 snapshot bound.
- No new data path; the `home_service` fan-out is unchanged (D-033).
- No tenant-configurable tabs in v1.
- No removal of any module.

## Open architectural questions

- **A-Q13.** Three tabs, or two (fold Costos y producción into Operación), or four (split logística and proveedores out). Fallback: three, re-grouped by observed use after 30 days, since it is one field edit. Panel source: Winston.
- **A-Q14.** Timonel column on the left or the right, and on mobile does it persist or collapse to a launcher. Fallback: right column on desktop, collapsible sheet on mobile.
- **A-Q15.** On Operación and Costos, tiles-with-drill-in or a primary module rendered inline with a sibling rail. Fallback: tiles with drill-in, the cheapest and the one that reuses the snapshots; revisit if the owner bounces too much.
- **A-Q16.** Does a money write through Timonel require a visible confirmation card on the active tab before it is considered done. Fallback: yes, surface the written row inline via `beans:refresh`; needs Edut and Mar'ah on the trust question raised in the review. Panel source: Winston, with Edut and Mar'ah.
