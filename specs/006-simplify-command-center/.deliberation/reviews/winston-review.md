# Winston review — Simplify the Command Center (AI-first, 1 to 4 tabs)

## 1. What problem is this actually solving?

The nine-entry rail is an engineering decomposition leaking onto the owner's screen. We built eight modules because eight is the right factoring of the code; the owner does not run eight systems, she runs one business, mostly alone, mostly by asking for things. The nav is an inventory of our modules, not a map of her jobs. The real job to be done: operate the whole business from one place, mostly by talking to Timonel, with the numbers visible and trustworthy enough to act on. Nine doors is navigation work she should not have to do.

## 2. What is the smallest first version that proves the idea?

Change the presentation layer only, nothing underneath. Add one `group` field to the module registry, render the rail as three job tabs (Hoy, Operación, Costos y producción), and promote Timonel from the bottom-right corner to a persistent primary column on the Hoy tab. Every route, API, provider, and the home fan-out stay exactly as they are. Ship it behind the pixel self-regression gate with the current home as golden. It proves the idea if the owner can run a full day (record a sale, add stock, log an expense, read cash and margin) from the Hoy tab, mostly by talking.

## 3. What 3 risks would kill this if ignored?

- Hiding money-writing CRUD behind chat. If a sale or expense lands with no visible confirmation on the surface, trust breaks the first time a number looks wrong, and it never comes back.
- Timonel write reliability. A conversational write to the ledger with no deterministic confirmation is a wrong row waiting to happen. The chat must show what it wrote, on the tab, not only say it did.
- Reshuffling without reframing. If three tabs are just the same eight pages behind fewer doors, the owner is no better off. The grouping must map to jobs and the chat must actually drive the work, or we have moved deck chairs.

## 4. What does success look like at 90 days?

The owner reaches everything through three tabs, lands on Hoy, and does most daily operations by talking to Timonel while the status tiles and attention strip stay visible and correct. The detail pages have become confirmations and drill-downs, not the primary input. No regression in any number versus today. The attention strip is still the one morning signal she trusts.

## 5. What atomic tasks does this break into?

1. Add a `group` field to the `Module` descriptor and populate three groups in `registry.py`; no route change.
2. Render the rail and mobile nav as grouped tabs in `cc_base.html`, driven off the registry groups.
3. Promote the Timonel slot to a persistent layout column on desktop, dismissible sheet on mobile; factory unchanged.
4. Compose the Hoy tab: status home tiles plus attention strip plus the Timonel column as the primary action surface.
5. Extend `beans:navigate` to carry `{tab, module}`; add the small shell tab-router that switches tab then drills in.
6. Keep `beans:refresh` per-surface; wire a visible post-write confirmation card for money writes on the active tab.
7. Group `home_service.build_home` output by the registry `group` field; render per-tab tile subsets with no new query.
8. Compose Operación and Costos tabs as their modules' tiles with drill-in to the existing pages.
9. Ensure each module page renders inside its tab context (back-to-tab, breadcrumb).
10. Mobile layout: tab bar plus chat sheet; verify no horizontal scroll.
11. Run the pixel self-regression gate over the reshaped shell, home as golden.

## 6. The one thing only an architect would notice

A tab is not a new concept here. The registry is already the single source of module truth (D-020, D-026), so a tab is a grouping attribute over it, one descriptor field, and the entire reshape is presentation plus that field, with zero change to routes, APIs, providers, `home_service`, or auth. The trap is anyone proposing to merge the eight pages into one. That breaks the three-read-layer split (D-025) and the one-Alpine-factory-per-page convention, re-couples the home the registry just decoupled, and throws away proven CRUD. Keep the pages. Group their doors.
