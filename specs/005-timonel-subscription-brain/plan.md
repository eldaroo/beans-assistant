# Plan 005: Timonel on the Claude subscription engine

Derived from `spec.md` by `/develop --headless` on 2026-10-15. Run id
`timonel-subscription-brain-20261015-141609`. Owner: Dario.

This spec is a BACKEND SWAP: every Timonel LLM call (Router, Resolver fallback, Read,
Decomposer) moves from Gemini to a shared Claude subscription gateway running warm in Nomad. The
agent architecture, schemas, and the deterministic Resolver path stay exactly as they are. Only
the model backend changes.

The whole-problem surface (s-01 .. s-08) is declared in `spec.md` under `## Whole-problem
surface`. s-07 and s-08 are tracked external deferrals (they need Dario's dedicated beans
`claude setup-token`, which the run cannot mint). Every other surface lands and is demonstrated
in this run.

## Milestones (cohort of 5, under the Section J cap of 10)

### M1: beans-ai gateway, Nomad jobspec + warm server (covers s-01, s-02)

`deploy/beans-ai.nomad.hcl` (a fork of `wal-parse.nomad.hcl`, warm variant) + `deploy/gateway.mjs`
(the warm server, embedded inline in the HCL and kept standalone for local test) +
`deploy/gateway.test.mjs` + `deploy/build-hcl.mjs` + `deploy/README.md`. The warm pool of
pre-spawned stream-json children (one logical turn per child) gives both warmth and multi-tenant
isolation; one-shot fallback when the pool is unavailable.

### M2: llm_gateway.py, HTTP client + LangChain ChatGateway (covers s-03)

`llm_gateway.py` + `tests/unit/test_llm_gateway.py`. The thin client POSTs `{system, prompt,
json_schema?}` to the gateway and exposes a LangChain `BaseChatModel` so each Timonel agent swaps
with a one-line backend change and the existing `JsonOutputParser` schemas stay untouched.

### M3: TIMONEL_LLM_BACKEND flag + dispatch in llm.py (covers s-04)

`llm.py` + `.env.example` + `tests/unit/test_llm_backend_flag.py`. `TIMONEL_LLM_BACKEND=gateway|
gemini` (global + per-tenant) dispatches `get_llm` / `get_llm_cheap`; Gemini stays the default and
the fallback. `get_llm_for_tools` (onboarding, out of scope) stays Gemini regardless.

### M4: per-call validation + fallback (covers s-05)

`llm.py` (fallback composition) + `llm_gateway.py` (validation helper, safe deterministic last
resort) + `tests/unit/test_llm_gateway_fallback.py`. On gateway error/timeout each agent falls
back to Gemini (during cutover) or a safe deterministic response, so Timonel never hard-fails on
the model path.

### M5: parity harness + fixtures (covers s-06)

`tests/eval/parity/harness.py` + `tests/eval/parity/run_parity.py` + `tests/eval/parity/
fixtures.json` + an optional `--backend gateway|gemini` on `tests/eval/{router,resolver,
decomposer}/run_eval.py` (default gemini, CI unchanged) + `tests/unit/test_parity_harness.py`.
Confirms the Claude path meets or beats Gemini on the known golden cases before per-tenant cutover.

## Out of scope

- Timonel's agent architecture, schemas, or the deterministic Resolver 90%-no-LLM path.
- The onboarding dispatcher (`backend/api/onboarding_web.py`, `get_llm_for_tools` + `.bind_tools`).
  It is the tenant-creation flow, not Timonel's brain, and relies on Gemini-style function
  calling. It stays Gemini-backed regardless of the flag; moving it onto the gateway is a later
  spec. **Why external:** named-human-signoff, since Dario decides whether onboarding joins the
  gateway (it changes the function-calling substrate).
- WhatsApp transport changes.
- Advanced pooling/concurrency beyond "warm pool, fresh child per turn, respawn on death".
