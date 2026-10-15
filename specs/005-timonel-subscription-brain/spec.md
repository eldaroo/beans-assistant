# Spec 005: Timonel on the Claude subscription (our Nomad engine), replacing Gemini

> Proposed 2026-10-15. Owner: Dario. Status: draft, ready to `/develop`.

## Problem

Timonel — the Control Center's embedded assistant (spec 004 puts it on every page) —
runs its multi-agent brain on **Gemini via a Google API key**: Router (intent
classification), Resolver (product resolution, deterministic + LLM fallback), Read
(analytics, chain-of-thought), Write (sales/expenses/inventory extraction). That is a
per-call metered external dependency on a different stack from the rest of the org's AI.

We just proved a pattern on **Wal Ledger** that works very well and that Dario wants to
reuse: a Claude **subscription** living in a Nomad job (NO API key), driving the Claude
Code CLI headless, behind a thin bearer-gated HTTP endpoint. Dario: *"yo reemplazaría la
lógica existente por la nuestra que funciona muy bien."*

## Why now

Spec 004 is making Timonel present on every Control Center page — its brain is about to be
load-bearing for the whole owner surface. Moving it onto the subscription engine now, before
Timonel's footprint grows, gives one consistent, no-API-key AI substrate across Wal, Beans,
and future products, and removes the Gemini key and its per-call cost.

## What this does

Replace every Timonel LLM call (Router, Resolver fallback, Read, Write) with a call to a
shared **subscription gateway**: a Nomad job holding a Claude subscription token, running a
**warm** `claude` process, exposing `POST /run {system, prompt, json_schema?}` over Traefik
+ TLS, bearer-protected. Timonel's Python agents swap their Gemini client for an HTTP call to
the gateway. The multi-agent orchestration, the schemas, and the 90%-deterministic Resolver
stay exactly as they are — **only the model backend changes.**

This is a BACKEND SWAP, not a feature or an architecture change.

## Two things the gateway MUST have that Wal's thin box did not need

1. **Warm / persistent process (mandatory).** Timonel is conversational and multi-agent: one
   user message fires several model calls (router + resolver + read/write). One-shot
   `claude -p` is ~6–8s cold, so a turn would be 20s+ — unusable in a chat. The gateway keeps
   a warm Claude process (`claude -p --input-format stream-json --output-format stream-json`)
   so each `/run` is ~2–3s. Each `/run` is a **fresh logical turn with no retained history**,
   so one tenant's prompt never sees another's (multi-tenant isolation).
2. **Dedicated token (or the pool).** Multi-tenant chat volume must not drain the token shared
   with Quinn and Wal. Beans gets its own `setup-token` (Dario generates it via
   `claude setup-token`), or wires the existing `QUINN_TOKEN_POOL` rotation. Not piggyback.

## Scope

### In scope

- **`beans-ai` Nomad job** (fork the `wal-parse` / `quinn-full` shape, in
  `clients/personal/wal-ledger/deploy/wal-parse.nomad.hcl` as the reference):
  - Positive-allowlist secret template: ONLY `CLAUDE_CODE_OAUTH_TOKEN` (Nomad Variable
    `nomad/jobs/beans-ai`, a dedicated beans token) + `BEANS_AI_SHARED_SECRET` (bearer). No org
    keyring; isolation self-check fails closed.
  - A warm persistent `claude` child; `POST /run {system, prompt, json_schema?, max_tokens?}`
    → `{ok, text | json}`; `GET /health`; bearer auth; Traefik route + LE TLS at
    `beans-ai.mdlautomations.duckdns.org`. Respawn the child if it dies; one-shot fallback.
- **A thin Python client in beans** (`llm_gateway.py`) exposing the SAME interface the current
  Gemini client exposes, so each agent swap is a one-line backend change (Router, Resolver
  fallback, Read, Write).
- **A backend flag** (`TIMONEL_LLM_BACKEND=gateway|gemini`, per-tenant or global) so cutover is
  reversible and Gemini stays as a fallback during migration.
- **Per-call response validation + fallback:** each agent re-validates the gateway output
  against its existing structured-output schema; on gateway error/timeout the agent falls back
  to Gemini (during cutover) or a safe deterministic response — Timonel never hard-fails on the
  model path.
- **Parity fixtures:** a set of real Timonel turns (intent classification, product resolution,
  analytics) run through both backends to confirm the Claude path matches or beats Gemini on
  the known cases *before* flipping the flag per tenant.

### Out of scope

- Changing Timonel's agent architecture, schemas, or the deterministic Resolver (the 90%
  no-LLM path stays).
- Any new assistant capability (this spec is strictly a model-backend swap).
- WhatsApp transport changes.
- Hardening the warm process beyond "one persistent child, fresh context per call, respawn on
  death" — advanced pooling/concurrency is a later spec.

## Architecture notes

- **Gateway**: a Node `node:http` server (like `wal-parse`) holding a long-lived
  `claude -p --input-format stream-json --output-format stream-json` child. Each `/run` writes
  one user message (system + prompt) to the child's stdin as a fresh turn and reads the JSON
  response. No history is retained between calls — critical for multi-tenant isolation.
- **Isolation**: stateless per-call; the secret allowlist carries no org data; the job holds no
  DB and reads no tenant data (it only transforms text the caller sends).
- **Token**: Nomad Variable `nomad/jobs/beans-ai` → `CLAUDE_CODE_OAUTH_TOKEN` (dedicated beans
  `setup-token`) + `BEANS_AI_SHARED_SECRET`. If using the pool instead, set `QUINN_TOKEN_POOL=1`
  + a reachable pool DB. Deploy via the Nomad HTTP API (`addr`/`token` in
  `.qie/secrets/credentials.yaml` `nomad:` block): `POST /v1/jobs/parse` (HCL→JSON) then
  `POST /v1/jobs`; set the Variable via `PUT /v1/var/nomad/jobs/beans-ai`.
- **Latency budget**: target ≤3s per warm call; a 2–3 call turn ≈ a few seconds. If a call
  exceeds a cap, the agent falls back (Gemini during cutover). Keep the deterministic Resolver
  path — only the <10% ambiguous resolutions and the genuinely-LLM agents hit the gateway.
- **Usage/cost**: the subscription usage window is the new limiter; monitor via the existing
  `claude-usage` / `everyset-claude-cost` jobs. The dedicated token bounds the blast radius.

## Risks

- **Volume exhausting the subscription** → dedicated token + usage monitoring; pool rotation as
  hardening.
- **Latency on multi-call turns** → warm process is mandatory; consider collapsing agents /
  fewer model calls per turn.
- **Multi-tenant prompt leakage** → stateless per-call with fresh context; verify no history
  carries between `/run` calls.
- **Model-behavior drift vs Gemini** (a different model classifies/extracts differently) →
  parity fixtures + the backend flag + per-agent fallback before full cutover.

## Acceptance (sketch)

1. `beans-ai` deployed, healthy, bearer-gated, TLS; `/run` returns valid structured output for
   the fixture prompts in ≤3s warm.
2. `llm_gateway.py` lets each Timonel agent call the gateway; `TIMONEL_LLM_BACKEND` flips the
   backend; Gemini fallback intact.
3. Parity fixtures pass: the Claude path ≥ Gemini on the known-case set (intent, resolution,
   analytics).
4. A real tenant Timonel turn (intent → resolve → read/write) completes end-to-end on the
   Claude backend within acceptable chat latency.
5. No cross-tenant context leakage (stateless-per-call verified).

## Reference material

- The proven pattern: `clients/personal/wal-ledger/deploy/wal-parse.nomad.hcl` (thin Claude
  subscription endpoint) and `quinn-discord/deploy/quinn-full.nomad.hcl` (the subscription-in-
  Nomad shape, warm `claude -p` over a queue).
- The warm-process idea (`--input-format stream-json`) is the upgrade Wal deferred; this spec is
  the first place it becomes mandatory.
- Nomad deploy mechanics + the shared subscription token live in `.qie/secrets/credentials.yaml`
  (`nomad:` block) and the `quinn-full` Nomad Variable.
