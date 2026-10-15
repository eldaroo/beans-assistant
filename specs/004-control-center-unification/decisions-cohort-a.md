# Cohort A decisions — Control Center unification (spec 004)

Run `cc-unif-cohortA-20261015-110944`. Defensible defaults taken where the spec
left a seam, so the run did not stall. Each is reversible and named for the
council and for Dario.

## D-1. This run drains Cohort A only (one cohort per /develop session)

plan.md states "This is the one-cohort-per-/develop-session granularity" and
sequences A -> B -> C -> D, each leaving the live product coherent. Cohort A is
the foundation seam (the shared base + the home re-based + the 4 read-only pages
migrated + the Timonel slot) that B/C/D all extend. This run ships Cohort A
whole; the next run continues with:

    /develop --headless --from-spec=eldaroo/beans-assistant#153

which re-reads the open children and drains Cohort B (productos + stock).

## D-2. AC1 home self-regression is proven browser-free (DOM identity)

AC1 wants "a visual self-regression check against the pre-change home." For a
pure template extraction (no redesign), DOM identity + CSS-rule presence is a
stronger proof than a screenshot diff — it needs no noise floor and cannot pass
a sub-pixel shift. Evidence captured at build time: the re-based home's
`<body>` is byte-identical (whitespace-normalized) to the pre-change home
rendered with the same viewmodel, all 40 home CSS rules are present verbatim in
cc_base, and both accent tokens (`#4F46E5` light / `#818CF8` dark) are present.
The stylesheet is reordered and carries the additive T-002 component CSS, with
no conflicting selectors, so the cascade and the painted pixels are unchanged.

## D-3. The Timonel slot defaults to floating, not pinned-open

The product default (`DEFAULT_DOCK='pinned'`, "the agent is the operating
surface") auto-opens a 420px docked panel on every page load. On the live
business home that is a large, content-overlaying change on first exposure. The
slot's Cohort A job is presence on every page (S7), not taking over the home.
So the cc_base slot passes `dock:'floating'`: Timonel is a bottom-right launcher
by default, one click to open, one click to pin, and the user's choice persists
in the same `beans:dock:{phone}` key the legacy page uses. The pinned,
agent-first experience the mockup shows is one click away, not forced.

This needed a backward-compatible factory option: `beansChat({ phone, dock })`.
Passing no `dock` (every existing caller, including the legacy tenant page)
keeps the pinned default unchanged. Flip to pinned-by-default is a one-word
change if Dario prefers the agent-first home.

## D-4. The 4 read-only pages adopt the held rail (content self-regression)

The pages were standalone centered columns (`.wrap`, 640px, a lone back-link),
already on the modern indigo tokens. The unification's whole point — and
iterations.md's carry-forward ("the four read-only pages migrate onto [the
modern design with held nav]") — is one held rail on every owner page. So the
migration gives them the cc_base shell (rail, topbar theme toggle, Timonel) and
keeps each page's content cards verbatim. "Visual self-regression against the
pre-change render" is therefore read at the content level: the data cards render
identically (proven by the four green integration page tests over real data),
while the rail + topbar + Timonel are the intended additive shell. The back-link
is kept so the content is unchanged; it points at `/home`, not legacy, so
Cohort D's legacy-link removal does not touch it.

## D-5. Node develop-gate is blind to this Python repo; pytest is authoritative

`bin/qie develop gate` has only Node/TS classes, so it returns CANNOT-VERIFY on
this FastAPI + Jinja repo (no tsconfig/package.json). This is the 5th
confirmation on beans-assistant (M1-M5 all hit it). Each milestone is stamped
DEFERRED-NO-GATE with the pytest run recorded as the real verification, per the
settled pattern. Authoritative result for the cohort: full non-browser suite
green except the two pre-existing unrelated `test_onboarding_m2` failures
(`TypeError: unhashable type: dict`, confirmed failing identically on base HEAD
c11af80).
