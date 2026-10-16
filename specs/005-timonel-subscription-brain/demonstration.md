# Timonel on the Claude subscription — spec 005 demonstration

This shows the backend swap running. Timonel's brain (Router, Resolver fallback, Read,
Decomposer) now runs on a warm Claude-subscription gateway instead of Gemini, selected by the
`TIMONEL_LLM_BACKEND` flag (global or per-tenant), with a Gemini-then-safe fallback so it never
hard-fails.

**Acceptance status up front:** 2 of 5 spec acceptance criteria (#2 flag/fallback, #5 isolation)
are met and demonstrated in this run. The other 3 (#1 live deploy healthy+TLS, #3 live parity
Claude ≥ Gemini, #4 real-tenant turn on the live backend) are deferred to
eldaroo/beans-assistant#157 and #158 because they need Dario's dedicated beans `claude
setup-token`, which only he can mint. Everything buildable is built, tested, and demonstrated
against the working tree; the only thing not exercised live is the leaf `claude` model call on the
deployed box.

In the demonstration that leaf is stubbed by a deterministic Timonel classifier; the HTTP gateway,
the warm child pool, the stream-json protocol, the Python `ChatGateway`, the backend dispatch, and
the fallback are all the real production code.

## End-to-end: real gateway + real Python client

`python deploy/demo_drive.py` stands up the real `beans-ai` gateway on localhost and drives real
Timonel turns through `get_llm(backend=gateway)` → `ChatGateway` → HTTP `/run` → warm pool →
`JsonOutputParser`:

```
========================================================================
beans-ai gateway — spec 005 end-to-end demonstration
(real HTTP gateway + real Python ChatGateway; only the leaf claude call is stubbed)
========================================================================

[1] GET /health -> {"ok": true, "svc": "beans-ai", "pool": {"ready": 2, "target": 2}, "backend": "claude-subscription"}

[2] TIMONEL_LLM_BACKEND resolves to: gateway  (no GOOGLE_API_KEY set)
    Driving real Timonel turns through the gateway (PROMPT | ChatGateway | JsonOutputParser):
      'hola, buenas'                 -> {"intent": "GREETING", "confidence": 0.98}
      'vendí 2 pulseras negras'      -> {"intent": "WRITE_OPERATION", "operation_type": "REGISTER_SALE", "confidence": 0.95}
      'gasté 30 dólares en envíos'   -> {"intent": "WRITE_OPERATION", "operation_type": "REGISTER_EXPENSE", "confidence": 0.93}
      'cuánto facturé esta semana'   -> {"intent": "READ_ANALYTICS", "confidence": 0.92}
      'cuántas pulseras tengo'       -> {"intent": "READ_ANALYTICS", "confidence": 0.92}

[3] Gateway down + no Gemini key -> safe fallback returns: '{}'  (Timonel never hard-fails)

All demonstration steps completed.
```

Notes on the demonstration, so nothing reads as more than it is:
- The intents/operation_types shown are the keyword stub's output, not a real Claude
  classification. They use the real router shape (`WRITE_OPERATION` + a separate `operation_type`)
  so the pipeline is exercised exactly as production would drive it.
- The `/health` `backend` field is a static label in the server; during this stubbed run it does
  not reflect a live Claude backend.
- Step 2 proves the swap is transparent: the existing `PROMPT | llm | JsonOutputParser` shape and
  the existing schemas are untouched, and it needs no Gemini key. The client also carves the first
  JSON object out of a prose-wrapped reply, so a Claude turn that wraps its JSON still parses
  through the unchanged parser.
- Step 3 proves the never-hard-fail floor: gateway down and no Gemini key degrades to a safe empty
  object the agents read defensively (clarify), not a crash.

## Acceptance coverage

| Spec acceptance | Status | Shown by |
|---|---|---|
| 1. `beans-ai` deployed, healthy, bearer-gated, TLS; `/run` returns structured output | built; live deploy external (#157) | `deploy/beans-ai.nomad.hcl` + `GET /health` + `/run` above |
| 2. `llm_gateway.py` lets each agent call the gateway; `TIMONEL_LLM_BACKEND` flips it (global + per-tenant); Gemini fallback intact | **done** | step 2 + step 3; per-tenant routing wired through `ChatService` (graph cache keyed by backend) |
| 3. Parity fixtures pass: Claude path ≥ Gemini on known cases | harness done; live run external (#158) | `tests/eval/parity/` + dry-run wiring check |
| 4. A real tenant turn completes end-to-end on the Claude backend | demonstrated on stubbed leaf; live external (#158) | step 2 above |
| 5. No cross-tenant context leakage (stateless-per-call) | **done by design** | warm pool leases a fresh child per turn, disposes it, no retained history; tools disabled so an injected prompt cannot act on the box |

## Test tallies (all green, working tree)

```
gateway suite (node deploy/test.mjs)                       16 pass / 0 fail
new python suites (llm_gateway, flag+routing, fallback, parity)  green
existing beans chat-service regression (crash, envelope, pending-entities)  green
parity dry-run                                             wiring check (parity_ok is unconditional under --dry-run; the real comparison is #158)
```

## What is deferred, and why

- **Live `beans-ai` cluster deploy** (#157) and **the live parity / real-tenant turn** (#158) need
  Dario's dedicated beans `claude setup-token` in the Nomad Variable `nomad/jobs/beans-ai`, which
  only Dario can mint (`external: operator-credential`). Deploying with the shared Quinn/Wal token
  would violate the spec's own isolation requirement and drain that quota, so the box is held until
  the dedicated token exists. The full deploy recipe and the per-tenant cutover sequence are in
  `deploy/README.md`.
