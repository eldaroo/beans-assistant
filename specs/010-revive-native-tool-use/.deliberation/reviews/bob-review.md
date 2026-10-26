# Bob (Scrum Master) — Spec 010 review: sequencing & cohorting

My lens is flow. This arc is large but **not as large as it reads**: `deploy/beans-mcp.mjs` is already built end to end (all read + write-preview tools, egress guard, tenant pinned out of band, `op_token` stripped from the model, dispatcher), and `web/lib/ops/stage.ts` already re-derives resolution, grounded amounts, the verdict, ambiguity and `groundingCorpus`. The new work is mostly the **Next-side internal endpoints, the service-token auth path, and the gateway/route wiring**. Sequence to prove understanding (a read) before risking a write.

**1. Problem.** The propose-only parser dead-ends on anything outside N fixed ops — Timonel is "tonto". Revive a model that understands the whole message and chooses tools, on the proven two-phase write substrate.

**2. Smallest first version.** One READ tool round-trip: operator asks a stock question → Vercel route → `beans-ai` loop → MCP `read_stock` → Next internal read endpoint (service-token) → answer. No write. Proves the agent reads live data through the whole new path.

**3. Three risks.** (a) Headless permission auto-resolve — spike M1 task 1, gate the arc. (b) Synchronous Vercel→Nomad multi-turn loop vs the route timeout. (c) Operator-turn grounding failing to reach `computeVerdict`, letting a model-invented numeral auto-post.

**4. 90 days.** The three core jobs (sale, expense, status) are daily habit; reversible writes auto-post with a loud Undo; irreversible are confirm-only; parser deleted; zero silent wrong commits.

## 5. Atomic tasks and milestone cohorts

Lead with the cheap high-visibility win (READ). Writes layer on after the two-phase path exists. Flag: tasks marked ⚠ exceed ~8h and must be split before drain.

**M1 — READ round-trip proven end-to-end (6 tasks).** *Boundary: smallest honest slice that proves understand+read on the new stack.* Ships: a live chat answering a stock question through gateway+MCP+Next.
- s1 Spike headless `--allowedTools` auto-approve; gate arc on result [human: operator-run spike]
- s2 Internal service-token auth path on Next, read-scoped, tenant pinned out of band [autodev]
- s3 `/internal/ops/read_stock` wrapping the domain read [autodev]
- s4 ⚠ Route seam: swap `parseMessage`→`beans-ai` loop behind a flag, keep parser fallback [autodev] — split from s5
- s5 ⚠ Serverless→Nomad synchronous call + timeout/fallback handling [autodev]
- s6 Gateway boot tool-posture self-check + egress allowlist to Next host [autodev]

**M2 — Full read surface (5 tasks).** *Boundary: read value complete, still zero write risk.* Ships: agent answers any business question.
- revenue/profit/sales_summary/read_module(×8)/business_status endpoints [autodev]; tool-selection prompt + no-tool smalltalk fallback [autodev]; live latency/turn-cap calibration [human].

**M3 — Write service-token path + first reversible preview (6 tasks).** *Boundary: the hard dependency — the internal service-token path on `/api/ops/stage` must land here before any write-preview tool can round-trip.* Ships: "vendí 3 a 400" stages a preview, confirm card renders, `/api/ops/confirm` commits.
- Service-token (no-session) path on `/api/ops/stage` [autodev, hard dep]; MCP arg→registry arg mapping (`product`→`productRef`, `unit_amount`→cents) [autodev]; ⚠ operator-turn grounding plumbed via `flow-turns.ts` → `groundingCorpus` [autodev]; `register_sale` preview endpoint [autodev]; confirm-card render reuse [autodev]; Edut consent sign-off on the write model [human].

**M4 — Reversible set + auto-post/Undo reuse (4 tasks).** *Boundary: the daily-habit jobs with safety.* Ships: obvious reversible writes auto-post with loud Undo.
- `register_expense`, `add_stock` endpoints [autodev]; auto-verdict wiring (grounded+single-candidate+caps) [autodev]; `/api/ops/undo` + pessimistic post reuse [autodev]; Kaze walk of cards/Undo [human].

**M5 — Irreversible/bulk confirm-only + hardening (6 tasks).** *Boundary: full op coverage behind human gates.* Ships: every op wired; security controls green.
- price/product/batch/deactivate/cancel endpoints [autodev]; per-session+global caps, tighter on cancel/deactivate [autodev]; append-only audit of tool calls + write intents [autodev]; injection-corpus test (injected write → `auto:false` + human card) [autodev]; security sign-off [human].

**M6 — Retire parser + deploy/verify (4 tasks).** *Boundary: loop is default, old brain gone.* Ships: prod read + confirmed write live.
- Remove parser path + beans-parse refs [autodev]; deploy gateway + command center [autodev]; Dario mints beans `claude setup-token` [human]; prod read+write verification [human].

**6. What only a Scrum Master noticed.** The arc front-loads its risk correctly only if M3's service-token path lands as its own task *before* any write tool — otherwise the three write cohorts all block on one unestimated seam and the burndown flatlines mid-arc. And because `beans-mcp.mjs`/`stage.ts` already exist, the real estimable work is endpoints + auth + wiring, not rebuilds; size the cohorts to that reality, not to the scary-sounding feature list.

---
**Cohort summary (2 lines):** M1 read-only proves the full new path cheaply; M2 completes reads at zero write risk. M3 lands the service-token hard dependency + first reversible write; M4 adds auto-post/Undo for the core jobs; M5 wires irreversible/bulk behind human gates with security; M6 retires the parser and ships to prod.
