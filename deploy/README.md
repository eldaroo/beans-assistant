# beans-ai — warm Claude-subscription gateway for Timonel

Spec: `specs/005-timonel-subscription-brain/`. This is the Nomad box that holds a Claude
subscription (no API key) and serves Timonel's model calls behind a bearer-gated HTTPS
endpoint. It replaces Gemini for Timonel's brain (Router, Resolver fallback, Read, Decomposer).

## Files

| File | Role |
|---|---|
| `gateway.mjs` | The warm gateway server. Single source of truth; also the local-test target. |
| `beans-ai.nomad.tmpl.hcl` | Job shell with the embed marker. Edit this, not the generated `.hcl`. |
| `build-hcl.mjs` | Embeds `gateway.mjs` into the template → `beans-ai.nomad.hcl`. Run after any edit. |
| `beans-ai.nomad.hcl` | **Generated.** The job submitted to Nomad. Do not hand-edit. |
| `gateway.test.mjs` | Offline tests (no `claude`, no token). Includes the HCL-sync and structural checks. |

Regenerate + test after editing `gateway.mjs` or the template:

```bash
node deploy/build-hcl.mjs
node deploy/gateway.test.mjs
```

## The warm design (why this is not wal-parse)

Timonel fires several model calls per user turn (router + resolver + read), so a one-shot
`claude -p` cold start (~6-8s each) would make a turn 20s+ — unusable in chat. The gateway keeps
a **pool of pre-spawned, idle** `claude -p --input-format stream-json --output-format stream-json`
children. Each `/run`:

1. leases a fresh warm child (already past CLI init),
2. writes exactly ONE user turn (`system + prompt` combined),
3. reads the stream to the `result` event and returns the text,
4. disposes that child and async-spawns a replacement into the pool.

One logical turn per child gives BOTH warmth (~2-3s, no cold start) AND zero cross-turn history,
which is the multi-tenant isolation guarantee: one tenant's prompt can never reach another's
turn. If the pool is empty or a warm lease errors/time-outs, the request falls back to a one-shot
`claude -p --output-format json` (the wal-parse path), so a transient pool problem never hard-fails.

## HTTP contract

- `GET /health` → `{ok:true, svc:"beans-ai", pool:{ready,target}, backend}` (Nomad check).
- `POST /run` (bearer required) with `{system, prompt, json_schema?, max_tokens?}` →
  - `{ok:true, path:"warm"|"one-shot", text}` (default), or
  - `{ok:true, path, json}` when `json_schema` is set (server carves the first JSON object), or
  - `{ok:false, error:{code, message}}` on `unauthorized` / `bad-json` / `empty-prompt` /
    `no-json` / `model-error`.

## Isolation invariant (load-bearing)

The secret template is a POSITIVE ALLOWLIST carrying exactly two inert values:
`CLAUDE_CODE_OAUTH_TOKEN` (a **dedicated** beans subscription token — not the shared Quinn/Wal
token) and `BEANS_AI_SHARED_SECRET` (the bearer). The entrypoint's isolation self-check greps the
env for any org-keyring shape (`GITHUB_/SUPABASE_/VERCEL_/GOOGLE_/GEMINI_/...`) and **exits 1**
(fails closed) if one is present. The box holds no DB and reads no tenant data.

## Deploy recipe (operator — needs the dedicated beans token)

The token is `external: operator-credential`: it must be minted interactively by Dario. The
rest is a scripted Nomad-API deploy. `.qie/secrets/credentials.yaml` `nomad:` block has `addr`
and `token`.

```bash
# 1. Dario mints a dedicated beans subscription token (interactive, one time):
claude setup-token            # copy the token it prints

# 2. Pick a random bearer:
BEARER=$(openssl rand -hex 24)

# 3. Set the Nomad Variable (positive allowlist):
curl -sS -H "X-Nomad-Token: $NOMAD_TOKEN" -X PUT "$NOMAD_ADDR/v1/var/nomad/jobs/beans-ai" \
  -d "{\"Path\":\"nomad/jobs/beans-ai\",\"Items\":{\"CLAUDE_CODE_OAUTH_TOKEN\":\"<token-from-step-1>\",\"BEANS_AI_SHARED_SECRET\":\"$BEARER\"}}"

# 4. Parse HCL -> JSON, then submit:
node deploy/build-hcl.mjs
JOBJSON=$(curl -sS -H "X-Nomad-Token: $NOMAD_TOKEN" -X POST "$NOMAD_ADDR/v1/jobs/parse" \
  -d "{\"JobHCL\":$(python3 -c 'import json,sys;print(json.dumps(open("deploy/beans-ai.nomad.hcl").read()))'),\"Canonicalize\":true}")
curl -sS -H "X-Nomad-Token: $NOMAD_TOKEN" -X POST "$NOMAD_ADDR/v1/jobs" -d "{\"Job\":$(echo "$JOBJSON" | python3 -c 'import json,sys;print(json.dumps(json.load(sys.stdin)))')}"

# 5. Verify healthy + TLS:
curl -fsS https://beans-ai.mdlautomations.duckdns.org/health
# 6. Hand $BEARER to the beans app as BEANS_AI_SHARED_SECRET and set
#    TIMONEL_LLM_BACKEND=gateway + BEANS_AI_GATEWAY_URL=https://beans-ai.mdlautomations.duckdns.org
```

Until step 1 is done the box cannot authenticate to Claude, so the deploy is held. The deploy
handoff is tracked in eldaroo/beans-assistant#157; the live parity run and the per-tenant cutover
are tracked in eldaroo/beans-assistant#158.

**Cutover sequence (after the box is healthy):**
1. Run the live parity check: `python tests/eval/parity/run_parity.py` (not `--dry-run`). It must
   report `parity_ok=True` before any tenant is flipped.
2. Flip ONE tenant first with `TIMONEL_LLM_BACKEND_<TENANT>=gateway` (the tenant key is the
   normalized phone, non-alphanumerics to `_`, uppercased), watch it, then widen.
3. Roll back instantly by clearing that tenant's flag or setting the global
   `TIMONEL_LLM_BACKEND=gemini`. The graph cache is keyed by backend, so the next request routes
   to the other backend with no restart.
