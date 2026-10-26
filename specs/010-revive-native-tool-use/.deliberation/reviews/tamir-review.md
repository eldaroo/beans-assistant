# Tamir — Rooted Shield (threat-model lens). Spec 010, Timonel native tool-use revival.

*The roots hold; the shield stands; what grows here grows for all.*

A tool-use agent is a larger attack surface than a propose-only parser: 008 went dumb on purpose, to take the choice-to-write away from the model. Reviving the agent reopens that door. The question is not "can it commit" (it cannot) but "can the model, or a leaked token, cause a write the operator never consented to." On the new stack that collapses to two seams.

**1. What problem this solves.** Real: the parser dead-ends on anything outside N fixed ops; the founder wants an agent that understands the whole message. Legitimate. My job is to make the tools-enabled box defensible on Vercel/Neon, not re-litigate the choice.

**2. Smallest first version.** One read round-trip (operator asks stock → gateway → `mcp__beans__read_stock` → `/internal/ops/read_stock` with service token, tenant pinned out of band → number back), then one write-preview that stages a `pending_ops` row and an `op_token` the model never sees, verdict `auto:false`, confirm card rendered. That vertical slice proves the service-token path, the out-of-band tenant, and the two-phase spine without opening the auto-post door.

**3. The 3 risks that would kill this.**

(a) **Provenance laundering via the internal stage path.** `computeVerdict` auto-posts when every numeral is grounded in `corpus`. Today `/api/ops/stage/route.ts` passes `body.utterance` and sets **no** `groundingCorpus` — it grounds against client-supplied text. Copy that to the internal MCP path and auto-post is forged: the model echoes its invented amount into the tool arg *and* into "utterance", both match, it auto-submits. The corpus MUST be server-authenticated operator words only (`groundingCorpusFor(owner, x-beans-turn)` via `flow-turns.ts`), never any MCP-body text. This is the whole ballgame.

(b) **Leaked `INTERNAL_SERVICE_TOKEN`.** It must be read-plus-propose only — reaches `/internal/ops/*` and `/internal/ops/preview/*`, DENIED at `/api/ops/confirm`/`undo`. A leaked token then stages inert previews (op_token never returns to a browser; commit needs the operator's session click), worst case a DoS on `pending_ops`. If confirm ever grows a service-token path, the surface is total.

(c) **Egress bypass at the dependency layer.** `isEgressAllowed` is in-code and a compromised npm dep calling `fetch` directly sails past it. The Nomad firewall (deny-all except the ops host + `api.anthropic.com`) is the load-bearing control; the JS allowlist is a backstop.

**4. Success at 90 days.** Agent handles the whole message; zero committed write without an operator session POST; the injection corpus stays green; audit shows every auto-post grounded in a recorded operator turn; no third-host egress; boot self-check has fail-closed at least once on a claude upgrade and been caught.

**5. Atomic tasks → required ACs (new stack).**

- **AC-T1** Service token read-plus-propose only: confirm/undo reject the service token (401); a preview writes `pending_ops` only, never a sales/expense/stock row.
- **AC-T2** Tenant from `x-beans-tenant` (gateway `BEANS_TENANT_PHONE`), never body/tool-arg; a body-set tenant is ignored.
- **AC-T3** Internal grounding = `groundingCorpusFor(owner,nonce)` ONLY; a body-echoed numeral absent from `operator_turns` yields `auto:false`.
- **AC-T4** Only the authenticated chat route appends `operator_turns`; its minted nonce == the forwarded `x-beans-turn`; cross-owner nonce reuse → empty corpus.
- **AC-T5** Port 007 AC9 injection corpus: a read-tool instruction to write neither commits nor auto-posts; built-in invocation denied.
- **AC-T6** Per-turn/per-session write caps at stage time (tighter on cancel/deactivate); one grounded turn cannot fan out past the cap; every tool call + write intent audited with the nonce.
- **AC-T7** Nomad egress firewall deny-all except ops host + Anthropic, live-tested; `verifyEgressConfig` fail-closed.
- **AC-T8** Boot `verifyToolMode` runs the exact production argv (allowlist `mcp__beans__*`, full disallow superset, `--strict-mcp-config`, NO skip-permissions); exits non-zero unless callable set is exactly `mcp__beans__*`; one child per request SIGKILL-disposed.

**6. The one thing only I catch.** Everyone checks "commit is non-model" and stops. The real exposure is **auto-post**, which bypasses the human entirely (the client auto-submits `/chat/confirm`), so the entire write surface's safety reduces to one predicate: *is `computeVerdict`'s `corpus` the operator's server-authenticated words?* And a second, subtler edge — `numeralIsGrounded` tests set **membership, not consumption**. One operator turn naming "400" and two products lets the model stage two auto-posting sales; nothing but the per-turn write cap bounds the fan-out. Auto-post consent is per-utterance (Edut's line); a membership check turns one utterance into N consents. AC-T3 and AC-T6 together are the only thing that holds the line.

---

**Threat summary (2 lines):** Reviving the agent is defensible only if auto-post grounds against the server's own `operator_turns` record (never MCP-body text) and the service token is read-plus-propose with commit permanently non-token — AC-T3, AC-T1, AC-T8 are load-bearing. The quiet killer is auto-post fan-out: grounding is membership-not-consumption, so one operator turn can authorize many writes unless a tight per-turn cap (AC-T6) bounds it.
