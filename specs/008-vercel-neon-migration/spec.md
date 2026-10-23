---
date: 2026-10-22
slug: 008-vercel-neon-migration
status: scoped
tracking_issue: eldaroo/beans-assistant#215
---

# Spec 008: Rebuild Beans & Co on the wal-ledger pattern (Vercel + Neon + Nomad parser)

## Problem

Beans & Co "feels slow" in both places the founder touches it: logging in and seeing the first page (~1s floor, measured 2026-10-22) and waiting for the chat to answer (a trivial agent turn is 4.4s, real tool turns 8–15s). Neither is a code bug. The login/first-page floor is physics: the origin is a single `uvicorn` box in St. Louis with no edge in front, so every request from Argentina pays a full TLS handshake across ~150–220ms of distance. The chat floor is architecture: every message spawns a fresh `claude` child on the gateway box, connects an MCP server, and runs a 6-turn tool loop that reaches back into the app's DB for each tool — a ~4s cold-start before a word is generated.

Underneath that, the app still carries three whole subsystems that belong to a business Beans no longer is: a **multi-tenant** Postgres and the ~60 files coupled to `tenant`/`phone`, a **WhatsApp** channel (Baileys), and a tenant **onboarding** flow. Beans is one business with one owner. All three are dead weight that make every change slower and riskier.

Dario's decision (2026-10-22, verbatim): Beans should stop being a multi-tenant Python multi-service app and become what wal-ledger is — a Next.js app on Vercel that owns its own database and hits a thin AI service on Nomad only to parse language into a proposal. That rebuild fixes both slownesses at the root (Vercel edge kills the login floor; a warm stateless parser + local Neon writes kill the chat floor) and deletes roughly half the codebase.

## Why now

The incremental patches (Cloudflare in front of the St. Louis box for login; warming the agent process for chat) would buy most of the speed in a few days but keep the legacy architecture — multi-tenancy, WhatsApp, onboarding, and a tool-wielding agent that holds DB credentials. Dario has decided to pay once for the right end-state instead of patching the wrong one. The target is already proven in production: wal-ledger runs this exact shape (Vercel + Neon/Drizzle + a detached, DB-less Claude `/parse` sidecar on Nomad) and is the app Dario pointed at as "funciona rápido, imitémoslo."

## The binding decision

Beans is rebuilt as a single-business application on the wal-ledger pattern. This is binding; this spec does not re-litigate it.

- **The Vercel app owns the database and all business logic.** Neon Postgres via Drizzle ORM. Every read and every write runs inside the Next.js app as a local serverless query. The app is the source of truth for every number; it never trusts the model's arithmetic (amounts are re-derived from the operator's text with a `lib/money.ts`, exactly as wal-ledger does).
- **The Nomad box is a dumb, stateless parser.** It receives operator text, returns a JSON *proposal*, and nothing else. It holds no database credential, reads no business data, has every built-in tool disabled, runs one turn, and is reached over HTTPS with a bearer. This replaces the current tool-wielding 6-turn gateway. The agent stops *operating* the business and only *proposes*; the app validates and executes.
- **Two-phase writes and the auto verdict are preserved** from spec 007: reversible + operator-grounded + in-cap writes auto-post with a loud Undo; everything irreversible, bulk, ambiguous, or un-grounded shows a confirm card. The verdict is computed by the app server-side, never by the model. The commit is never a model capability.
- **Single business, no tenancy.** No tenant columns, no `phone`-keyed scope, no onboarding. One owner, one dataset.
- **Drop WhatsApp entirely.** The command-center web surface is the only channel. (Gate G1 below: confirm with the owner that no live orders still arrive by WhatsApp before the channel is removed.)

## Target architecture

- **Next.js 15 App Router + React 19 on Vercel**, deployed under the `eldaroos-projects` Vercel account (eldaroo isolation rule). New app lives at `web/` in `eldaroo/beans-assistant`; the Python app stays runnable until cutover, then is removed.
- **Neon Postgres + Drizzle ORM**, one project, single-business schema (the nine domains below + an append-only `audit_log`), no tenant columns.
- **Auth: keep the existing Google OAuth** (owner's decision 2026-10-22). The new app reuses the current Beans Google OAuth client and allowlists the owner's account(s), enforced in Next.js middleware (NextAuth or equivalent). No new login for the owner. (D-008-01, resolved.)
- **Credentials are sourced from existing projects, never requested from the owner** (decision 2026-10-22): the Vercel token from the `eldaroos-projects` project set, the Neon provisioning token from the autodev management credential, and the Google OAuth client reused from the current Beans deployment env. The parser box uses the `claude` subscription on the Nomad host (no API key), exactly as wal-parse does.
- **The parser sidecar on Nomad**, patterned on `deploy/wal-parse.nomad.hcl`: inline `server.mjs`, warm pool of `claude -p` children, `--disallowedTools Bash,Edit,Write` (all tools off), no DB env, single bearer, reached at a `beans-parse.*` host. Degrades gracefully: when the box is down the app falls back to a local deterministic parser so capture never fully breaks.
- **Observability**: the canonical Light-Brands stack (Sentry + PostHog + Vercel Analytics + Speed Insights) wired at M0 per org standard.

## Scope

In scope:

- A new Next.js 15 App Router app on Vercel with the existing Google OAuth gate and the full observability stack.
- A Neon/Drizzle single-business schema covering products, stock, sales, expenses, costing + cost scenarios, production, suppliers, logistics, analytics, plus an append-only audit log; and a one-time migration of the single prod business's live data (`+54955885565`) from the current Postgres into Neon.
- The business logic of all nine domains ported Python→TypeScript into `lib/`, carrying forward every domain guard that exists today: the NULL-price write block, batch partial-success summaries, ADD_STOCK disambiguation, product resolution and SKU generation, landed-cost/costing math, and cost scenarios. Parity tests against the Python outputs.
- App Router route handlers for every domain: read snapshots for the module tabs, and two-phase writes (stage a validated `op_token`, commit through a non-model `/confirm`) with the named-error envelope `{ok:false,error:{code,message}}`.
- The command-center UI rebuilt in React: the `Hoy` dashboard with its tiles and the module pages (stock, productos, ventas, costos, produccion, proveedores, logistica, analytics, resultado).
- The chat widget rebuilt in React (Composer-style), carrying forward the shipped mic UX (live interim transcription, loud errors, `es-AR`) and the spec-007 confirm-card / settled-receipt / Undo model.
- The Nomad parser sidecar (wal-parse pattern), the app↔parser contract (text → proposal JSON), the server-computed auto verdict ported from wal-ledger's `numberTokens`, and the local deterministic fallback parser.
- A full parity test suite exercising every domain's read and write against the live Python app as oracle, and the cutover runbook.
- Retirement, at cutover, of: the Python FastAPI app and its Jinja templates, the tool-wielding gateway (`deploy/gateway.mjs`) and the `internal_ops` MCP callback layer, all multi-tenant coupling, the onboarding flow, and the WhatsApp (`whatsapp_baileys/`) channel.

Out of scope:

- Any multi-business / multi-tenant capability. One business, permanently.
- New operation types beyond today's menu. This ports the menu; it does not grow it.
- WhatsApp or any channel other than the web command center.
- Streaming token-by-token chat output (a later enhancement; the warm parser already removes the felt latency).
- Changing the business's accounting model, costing formulas, or module layout beyond what the port requires.

## Milestones

Each milestone is a cohort that ships demonstrably and deploys to a live Vercel URL Dario can open. `/develop --headless` drains them in order.

- **M0 — Shell + infra.** New Next.js 15 app at `web/`, Vercel project under `eldaroos-projects`, Neon project provisioned, edge-middleware auth gate (PIN default, D-008-01), observability stack wired. Deploys an authenticated empty shell to a live URL.
- **M1 — Schema + data migration.** Drizzle single-business schema for all nine domains + `audit_log`. One-time ETL of the live `+54955885565` data from current Postgres → Neon, with a row-count + spot-value reconciliation report. (Live final re-sync happens at M8.)
- **M2 — Business logic → TS.** Port the nine domains' logic into `lib/` with every guard preserved; `lib/money.ts` for independent amount re-derivation. Parity tests vs Python outputs green.
- **M3 — API routes.** App Router handlers: per-domain read snapshots + two-phase writes (`op_token` stage + non-model `/confirm` commit), named-error envelope, audit-log append on every write intent.
- **M4 — UI.** `Hoy` dashboard + the nine module pages rebuilt in React, reading the M3 snapshots, mobile-first (360px), Kaze doctrine applied.
- **M5 — Chat widget.** React Composer-style widget with the shipped mic UX and the spec-007 confirm-card / settled-receipt / loud-Undo model, wired to M3 writes.
- **M6 — Parser sidecar.** Nomad `beans-parse` job on the wal-parse pattern (stateless, DB-less, tools-off, warm pool, bearer); the text→proposal contract; server-computed auto verdict; local deterministic fallback. Widget → parser → app-validates-and-executes round-trip live.
- **M7 — Parity + hardening.** Full parity suite across every domain vs the live Python app as oracle; injection-corpus test proving no model-driven write commits without the app's own verdict; rate limits, egress posture, audit completeness.
- **M8 — Cutover (THE GATE).** Final live-data re-sync, DNS/host move, auth config, smoke across every domain, then retire the Python app, gateway, `internal_ops`, multi-tenant code, onboarding, and WhatsApp. This milestone is `human`-gated: it needs Neon prod credentials, DNS control, the owner's login change, and G1 (WhatsApp-off confirmation). `/develop` stamps it `Deploy DEFERRED: external` and hands the exact promote + cutover steps.

## Acceptance criteria

1. The app is a Next.js 15 App Router project on Vercel under `eldaroos-projects`, reachable at a live URL behind Google OAuth; an unauthenticated request to any app route redirects to Google sign-in and an allowlisted account renders.
2. Neon is the only datastore the app talks to; there is no `tenant`/`phone` column in any table and no code path reads a tenant from a request.
3. The M1 migration report shows row counts per domain matching the source Postgres within an explained delta, and a spot-check of stock-on-hand, last-N sales, and current costing for the live business matches the Python app's numbers.
4. Every ported domain in `lib/` has a parity test that feeds a fixture and asserts byte-equal (or explained-tolerance) output against the Python implementation, including the NULL-price block, ADD_STOCK disambiguation, product resolution/SKU generation, and landed-cost/costing + scenario math. The suite is green.
5. Every write route is two-phase: a stage endpoint returns a validated `op_token` and writes no row; a non-model `/confirm` is the single commit path; the parser has no capability that reaches `/confirm`. A double-commit is idempotent and returns the committed values read back from Neon.
6. The auto verdict is computed server-side: a reversible, operator-grounded ("registrá una venta por 400 de una tabla" with the amount matching a numeral and the product resolving to exactly one active candidate), in-cap write auto-commits with a loud Undo and no manual click; an irreversible, bulk, ambiguous, NULL-price, or bare-confirmation turn yields a confirm card. A test drives each falsifying case; the model never sets the flag.
7. The parser sidecar on Nomad spawns `claude` children with every built-in tool disabled, carries no DB credential in its environment, holds no business data, and returns only a proposal JSON; a posture self-check fails the boot otherwise, and an injection-corpus test proves no operator-text instruction causes a write without the app's own verdict + `/confirm`.
8. With the parser box stopped, the app still accepts a capture via the local deterministic fallback and records it; a test asserts the degraded path.
9. The chat widget renders the confirm card as a visually distinct species from the settled receipt, shows numeric arguments in digits, flags irreversibility, settles in place on commit, and carries the shipped mic UX (live interim transcription, loud errors, `es-AR`); verified in a live browser click-through at 360px and desktop.
10. A measured latency check from Argentina shows the authenticated first page and a trivial chat turn both materially faster than the current St. Louis/uvicorn + fresh-child baseline (first page well under the ~1s floor; a trivial parse well under 4.4s), recorded in the closing.
11. At cutover (M8) the Python app, `deploy/gateway.mjs`, `internal_ops`, all multi-tenant code, the onboarding flow, and `whatsapp_baileys/` are removed from the default branch, and every module's read and write works end-to-end on the new app against Neon under the moved domain.

## Open decisions (defensible defaults taken; owner may override)

- **D-008-01 — Auth. RESOLVED (2026-10-22):** keep the existing Google OAuth; reuse the current Beans OAuth client and allowlist the owner's account(s). No PIN gate.
- **D-008-02 — Domain/host. RESOLVED (2026-10-22): no Cloudflare.** Vercel's own edge is the speed win; the app is served from Vercel directly. At cutover a custom domain is pointed at Vercel (a `*.lightbrands.ai` subdomain as DNS-only or the existing name CNAME'd to Vercel) — no Cloudflare proxy/CDN in front. Exact host resolved at M8 with DNS access.
- **D-008-03 — Repo shape.** Default: new `web/` app in `eldaroo/beans-assistant` (preserves history); Python app removed at M8. Alternative: a fresh repo if the owner prefers a clean cut.

## Gates

- **G1 (human, pre-M8):** confirm with the owner that Beans & Co no longer receives orders via WhatsApp before the Baileys channel is removed. This is the only drop with real user impact.
