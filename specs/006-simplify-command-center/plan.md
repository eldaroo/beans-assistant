# Plan: Simplify the Command Center (AI-first, three tabs)

## Architecture sketch

This is a presentation reshape over an unchanged domain. The module registry stays the single source of truth; a tab is a grouping attribute over it. Timonel moves from a corner widget to a primary column but keeps its single mount and its factory. The chat-to-content bridge gains a tab dimension. The home fan-out is grouped, not re-run. The one genuinely new system is the AI-write trust floor (confirm, receipt, change history, undo), which wraps the existing chat write path rather than replacing it. Full decision log in ARCHITECTURE.md, D-029 through D-033.

```
cc_base.html (shell)
├── rail / mobile nav   <- three tabs from registry `group` field (S1)
├── Timonel column      <- single mount, primary on Hoy, sheet on mobile (S2)
│     ├── thread persist/rehydrate (sessionStorage + server thread) (S3)
│     └── write trust floor: confirm -> commit -> receipt -> history -> undo (S5)
├── tab content region
│     ├── Hoy        : daily-truth headline + status tiles + attention (S6)
│     ├── Operación  : productos, stock, ventas, resultado tiles -> drill-in pages
│     └── Costos y p.: costos, producción, logística, proveedores tiles -> drill-in
└── shell tab-router  <- consumes beans:navigate {tab, module} (S4)

home_service.build_home  <- one fan-out, output grouped by `group` (unchanged query path)
```

## Sequencing (milestone cohorts, <= 10 children each)

| Milestone | Theme | Covers | Rough effort |
|-----------|-------|--------|--------------|
| M1 | Three-tab shell, nav-only, reversible, no domain change | S1 | ~2 days |
| M2 | Timonel primary column, chat persistence, Hoy headline, tab contract | S2, S3, S4, part S6 | ~3 days |
| M3 | AI-write trust floor (confirm, receipt, change history, undo, thresholds) | S5 | ~3 days |
| M4 | Discoverability, honest fallback, mobile, instrumentation, usability check | S6, S7 | ~2 days |

M1 is a safe, reversible nav reshape that ships behind the pixel self-regression gate. M2 makes the AI primary, but only after M1 proved the shell. M3 is the trust floor and must land before the owner is encouraged to make Timonel the default write path; its threshold policy (AC9) is human-signed by Andreas and Edut. M4 closes discoverability, mobile, and the instrumentation that feeds the 30-day re-group decision in A-Q13. The T-000 mockup port is pinned to the top of M1 as the visual contract.

## Risks

1. **Chat state dies on navigation.** `chat_widget.js` resets `messages: []` on every load and persists only dock and greeting flags. If Timonel is made primary before the thread persists, the owner loses the conversation on every tab switch. Mitigation: ship thread persistence and rehydration (M2, AC4) before or with the column promotion; server thread (spec 001) as the fallback source.
2. **Trust in AI writes to money.** A conversational write to the ledger with no visible confirmation is a wrong row waiting to happen, and the harm lands on the one person not technical enough to audit it. Mitigation: the M3 trust floor (confirm-before-write, visible receipt, owner-readable change history, undo) ships before Timonel is positioned as the default write path; delete/cancel, stock-to-zero, over-threshold expense, price change, and inferred fields route to human review (AC9).
3. **Reshuffle without reframing.** If three tabs are just the same eight pages behind fewer doors, the owner is no better off. Mitigation: the grouping maps to jobs, the daily-truth headline and the Timonel primary column make the chat actually drive, and the pixel gate (AC12) proves no number regressed.
4. **Over-cutting and discoverability collapse.** Hiding capability behind chat means the owner stops knowing what the product can do, and the costing/supplier review surfaces rot if buried. Mitigation: keep all pages as drill-downs (D-032), add capability hints on Hoy, and an honest AI fallback that links the exact section; defer any page deletion to the 30-day observed-use re-group (A-Q13).
5. **Alpine state collision.** If the four pages of a tab are ever merged into one page, shared element ids and localStorage keys cross-contaminate. Mitigation: merging is a v1 non-goal (D-032); if pursued later, dedup element ids first.

## Dependencies

- Timonel chat write and read tooling over `/api/tenants/{phone}/chat` (spec 001, 005). Exists.
- The chat-to-screen bridge `cc_chat_bridge.js` (spec 004 cohort D). Extended here with `{tab, module}`.
- The server-side chat thread memory (spec 001) as the rehydration fallback when sessionStorage is empty.
- The pixel self-regression gate (`bin/qie pixel`) with the current home as golden.
- External decision: the AC9 threshold policy requires Andreas plus Edut sign-off before its children materialize.

## Cost-shaped considerations

Almost all of M1 and M2 is presentation and client-side state; the cost is attention, not infrastructure. M3 is the real engineering: the trust floor touches the chat write path and adds a change-history store (append-only, reusing the tenant schema). No new external service, no new LLM spend beyond the confirm and low-confidence re-ask turns.
