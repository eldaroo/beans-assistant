# beans-ai — a WARM Claude-subscription gateway for Timonel (spec 005).
#
# TEMPLATE. Do not edit deploy/beans-ai.nomad.hcl by hand: it is generated from this file and
# deploy/gateway.mjs by `node deploy/build-hcl.mjs`. The embed marker below (alone on its line)
# is where the gateway source is injected (indented to the heredoc). deploy/gateway.test.mjs
# asserts the committed .hcl is in sync with gateway.mjs, so the box and the tests never drift.
#
# A FORK of wal-parse (clients/personal/wal-ledger/deploy/wal-parse.nomad.hcl) with the warm
# process Wal deferred. Timonel fires several model calls per turn (router + resolver + read),
# so a one-shot cold start would make a turn unusable in chat; this box keeps Claude warm.
#
# LOAD-BEARING INVARIANT (same as wal-parse / quinn-full): the secret template is a POSITIVE
# ALLOWLIST. It carries exactly two inert values — CLAUDE_CODE_OAUTH_TOKEN (a DEDICATED beans
# subscription token, NOT the shared Quinn/Wal token) and BEANS_AI_SHARED_SECRET (the bearer).
# No org keyring, no DATABASE_URL, no GOOGLE/GitHub/Vercel/Supabase value ever lands here. The
# box reads NO tenant data: beans calls it with text and gets back text; the app owns the DB.
#
# Create the Nomad Variable before submitting (Dario generates the token via `claude setup-token`):
#   nomad/jobs/beans-ai -> { CLAUDE_CODE_OAUTH_TOKEN: <dedicated beans sub token>, BEANS_AI_SHARED_SECRET: <random> }
#
# Public URL (Traefik + Let's Encrypt, wildcard *.mdlautomations.duckdns.org):
#   https://beans-ai.mdlautomations.duckdns.org/run   (POST, bearer)
#   https://beans-ai.mdlautomations.duckdns.org/health (GET)

job "beans-ai" {
  datacenters = ["dc1"]
  namespace   = "default"
  type        = "service"

  meta {
    rev = "1"
  }

  # Co-locate on node2 (node1 is Nomad-memory-tight; quinn-full and wal-parse pin here too).
  constraint {
    attribute = "${attr.unique.network.ip-address}"
    value     = "80.241.214.201"
  }

  group "beans-ai" {
    count = 1

    update {
      max_parallel      = 1
      health_check      = "task_states"
      min_healthy_time  = "20s"
      healthy_deadline  = "5m"
      progress_deadline = "8m"
      auto_revert       = true
    }

    ephemeral_disk {
      size    = 600
      sticky  = false
      migrate = false
    }

    restart {
      attempts = 5
      interval = "30m"
      delay    = "15s"
      mode     = "delay"
    }

    reschedule {
      attempts       = 3
      interval       = "1h"
      delay          = "30s"
      delay_function = "exponential"
      max_delay      = "5m"
      unlimited      = false
    }

    network {
      port "http" {}
    }

    task "gateway" {
      driver = "docker"

      config {
        # Reuse the pre-baked brain image (git, Claude CLI, Node 22). force_pull picks up refresh.
        image      = "ghcr.io/light-brands/quinn-brain:latest"
        command    = "/bin/bash"
        args       = ["-c", "/local/entrypoint.sh"]
        force_pull = true
        ports      = ["http"]
      }

      # NON-SECRET env only. The two secrets live in the allowlist template below.
      env {
        HOME                = "/root"
        CLAUDE_BIN          = "claude"
        GIT_TERMINAL_PROMPT = "0"
        IS_SANDBOX          = "1"
        ALLOC_DATA          = "/alloc/data"
      }

      # POSITIVE ALLOWLIST (same discipline as wal-parse). With env=true every key is on its own
      # line; never place a {{- ... -}} comment between two KEY=VALUE lines (it merges them).
      template {
        destination = "secrets/beans-ai.env"
        env         = true
        change_mode = "restart"
        data        = <<-EOH
          {{- with nomadVar "nomad/jobs/beans-ai" -}}
          CLAUDE_CODE_OAUTH_TOKEN={{ .CLAUDE_CODE_OAUTH_TOKEN }}
          CLAUDE_CODE_OAUTH_TOKENS={{ .CLAUDE_CODE_OAUTH_TOKENS }}
          BEANS_AI_SHARED_SECRET={{ .BEANS_AI_SHARED_SECRET }}
          {{- end -}}
        EOH
      }

      template {
        destination = "local/entrypoint.sh"
        perms       = "0755"
        data        = <<-EOS
          #!/bin/bash
          set -euo pipefail
          ts()  { date -u +%Y-%m-%dT%H:%M:%SZ; }
          log() { echo "[beans-ai $(ts)] $*"; }

          if [ -z "$${CLAUDE_CODE_OAUTH_TOKENS:-}" ] && [ -z "$${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
            log "FATAL: no CLAUDE_CODE_OAUTH_TOKENS or CLAUDE_CODE_OAUTH_TOKEN present"; exit 1
          fi
          : "$${BEANS_AI_SHARED_SECRET:?BEANS_AI_SHARED_SECRET required}"
          : "$${NOMAD_PORT_http:?http port required}"

          # Isolation self-check: no org-keyring value may be present. Fail closed.
          log "isolation self-check: scanning env for org-keyring shapes"
          LEAK="$(env | grep -iE '^(GITHUB|SUPABASE|VERCEL|STRIPE|DATABASE|CLOUDFLARE|GOOGLE|GEMINI|SIGNNOW|LB_SHARE|OPENAI|DISCORD|NEON)_' || true)"
          if [ -n "$${LEAK}" ]; then
            log "FATAL: org-keyring value present, isolation broken:"
            echo "$${LEAK}" | sed 's/=.*/=<redacted>/' >&2
            exit 1
          fi
          log "isolation OK: env carries only the model token and the bearer"
          log "toolchain: node $(node --version) · $(claude --version 2>/dev/null | head -1)"
          log "starting warm gateway on :$${NOMAD_PORT_http}"
          exec node /local/gateway.mjs
        EOS
      }

      # The warm gateway. Shipped inline so the box needs no repo clone. Embedded from
      # deploy/gateway.mjs by deploy/build-hcl.mjs — DO NOT edit the generated .hcl copy.
      template {
        destination = "local/gateway.mjs"
        perms       = "0644"
        data        = <<-EOJS
          // deploy/gateway.mjs — beans-ai, a warm Claude-subscription gateway for Timonel.
          //
          // A FORK of wal-parse (clients/personal/wal-ledger/deploy/wal-parse.nomad.hcl) with the
          // one upgrade Wal deferred: a WARM process. Timonel is conversational and multi-agent —
          // one user message fires several model calls (router + resolver + read) — so a one-shot
          // `claude -p` cold start (~6-8s) would make a turn 20s+. This gateway keeps Claude warm.
          //
          // Endpoints:
          //   POST /run {system, prompt, json_schema?, max_tokens?} -> {ok:true, text} | {ok:true, json}
          //                                                          -> {ok:false, error:{code,message}}
          //   GET  /health -> {ok:true, svc:"beans-ai", pool:{ready, target}, backend}
          // Bearer auth: every /run requires `Authorization: Bearer <BEANS_AI_SHARED_SECRET>`.
          //
          // WARM + ISOLATED (the load-bearing design). A single long-lived `claude` conversation
          // retains history, which would leak one tenant's prompt into the next tenant's turn. So the
          // gateway keeps a POOL of pre-spawned, idle `claude -p --input-format stream-json
          // --output-format stream-json` children. Each /run LEASES a fresh child, writes exactly ONE
          // user turn (system + prompt combined), reads the stream to the `result` event, returns the
          // text, then DISPOSES that child and async-spawns a replacement into the pool. One logical
          // turn per child gives BOTH warmth (a ready child already paid the CLI init cost, so the turn
          // is ~2-3s not ~6-8s) AND zero cross-turn history (strict multi-tenant isolation). If the pool
          // is empty or a warm lease errors, the request falls back to a one-shot `claude -p
          // --output-format json` (the wal-parse path), so a transient pool problem never hard-fails.
          //
          // Testable offline: CLAUDE_BIN overrides the binary; gateway.test.mjs drives it with a stub
          // `claude` that speaks the stream-json protocol, so the full request path is exercised with no
          // subscription token and no network.
          
          import http from 'node:http';
          import { spawn } from 'node:child_process';
          import { timingSafeEqual } from 'node:crypto';
          import {
            detectExhaustion,
            cooldownReset,
            allExhaustedMessage,
            parseTokens,
            TokenPool,
            childSpawnEnv,
          } from './token-pool.mjs';
          
          const DEFAULTS = {
            poolTarget: 2, // warm children kept idle and ready
            runTimeoutMs: 55000, // hard cap on a single warm turn before falling back to one-shot
            oneShotTimeoutMs: 58000,
            maxPromptBytes: 200000,
          };
          
          // SECURITY (council, Tamir): Timonel needs PURE TEXT generation, nothing else. The gateway feeds
          // tenant-controlled text to the model, so a prompt-injection must never be able to make the model
          // act on the box. We therefore (a) do NOT pass --dangerously-skip-permissions, so in headless -p
          // mode any tool call is auto-denied (there is no TTY to approve it), and (b) explicitly disallow
          // every tool as defense-in-depth. A classification turn calls no tools; an injected one is denied.
          const DISALLOWED_TOOLS = [
            'Bash', 'BashOutput', 'KillShell', 'Edit', 'Write', 'Read', 'NotebookEdit',
            'WebFetch', 'WebSearch', 'Task', 'Glob', 'Grep',
          ];
          
          // Common args for a safe, tool-free Claude turn. Appended to the per-mode argv.
          const SAFE_ARGS = ['--disallowedTools', ...DISALLOWED_TOOLS];
          
          // Constant-time bearer comparison (council, Tamir LOW): avoid a byte-wise timing side-channel.
          function bearerOk(header, secret) {
            const expected = 'Bearer ' + secret;
            const a = Buffer.from(String(header || ''));
            const b = Buffer.from(expected);
            if (a.length !== b.length) return false;
            try {
              return timingSafeEqual(a, b);
            } catch {
              return false;
            }
          }
          
          // ── stream-json helpers ────────────────────────────────────────────────────
          
          // One user turn in `--input-format stream-json`: a single JSONL line.
          function userTurnLine(text) {
            return (
              JSON.stringify({
                type: 'user',
                message: { role: 'user', content: [{ type: 'text', text }] },
              }) + '\n'
            );
          }
          
          // Pull the assistant's final text out of a stream-json event stream. The CLI emits a trailing
          // `{"type":"result","result":"..."}`; prefer it, else fall back to concatenated assistant text.
          function extractResult(events) {
            for (let i = events.length - 1; i >= 0; i--) {
              const e = events[i];
              if (e && e.type === 'result' && typeof e.result === 'string') return e.result;
            }
            let acc = '';
            for (const e of events) {
              if (e && e.type === 'assistant' && e.message && Array.isArray(e.message.content)) {
                for (const block of e.message.content) {
                  if (block && block.type === 'text' && typeof block.text === 'string') acc += block.text;
                }
              }
            }
            return acc;
          }
          
          // Carve the first balanced JSON object out of a model reply (same contract as wal-parse). The
          // Python client re-validates against its Pydantic schema, so a loose field here never commits.
          function carveJson(text) {
            const m = String(text).match(/\{[\s\S]*\}/);
            if (!m) throw new Error('no json object in model output');
            return JSON.parse(m[0]);
          }
          
          // ── the warm child pool ─────────────────────────────────────────────────────
          
          class ChildPool {
            constructor(opts = {}) {
              this.claudeBin = opts.claudeBin || process.env.CLAUDE_BIN || 'claude';
              this.cwd = opts.cwd || '/alloc/data';
              this.target = opts.poolTarget ?? DEFAULTS.poolTarget;
              this.spawnChild = opts.spawnChild || this._defaultSpawn.bind(this);
              // Returns the active subscription token so each spawned child carries it; rotation takes
              // effect on the next spawn (and on rekey below). Null when no pool is wired (ambient token).
              this.tokenFn = opts.tokenFn || null;
              this.idle = [];
              this.closed = false;
            }
          
            _defaultSpawn() {
              // A warm child: print mode, stream-json in and out, permissions pre-granted. It sits idle
              // reading stdin until we hand it one user turn, then ends its own run.
              const child = spawn(
                this.claudeBin,
                [
                  '-p',
                  '--input-format',
                  'stream-json',
                  '--output-format',
                  'stream-json',
                  '--verbose',
                  '--max-turns',
                  '1',
                  ...SAFE_ARGS,
                ],
                // stderr is ignored (not piped): --verbose can exceed the OS pipe buffer and, undrained,
                // would block the child before it flushes the stdout result (council, Binyan).
                // env carries the active subscription token so a rotation reaches the next-spawned child.
                { cwd: this.cwd, stdio: ['pipe', 'pipe', 'ignore'], env: childSpawnEnv(process.env, this.tokenFn ? this.tokenFn() : null) }
              );
              child.on('error', () => {}); // surfaced by the lease, never crash the server
              // Evict a child that dies WHILE IDLE so the pool never reports a corpse as ready and never
              // leases a dead child into the one-shot cold path (council, Binyan).
              child.once('exit', () => {
                const i = this.idle.indexOf(child);
                if (i >= 0) {
                  this.idle.splice(i, 1);
                  this.refill();
                }
              });
              return child;
            }
          
            // Keep `target` children warm and ready. Called at boot and after every lease.
            refill() {
              if (this.closed) return;
              while (this.idle.length < this.target) {
                let child;
                try {
                  child = this.spawnChild();
                } catch {
                  break; // spawn failing (no binary) → pool stays small; /run falls back to one-shot
                }
                if (!child || !child.stdin) break;
                this.idle.push(child);
              }
            }
          
            lease() {
              const child = this.idle.shift() || null;
              // Replace what we took (or discovered dead) so the pool stays warm for the next caller.
              setImmediate(() => this.refill());
              return child;
            }
          
            get ready() {
              return this.idle.length;
            }
          
            // Dispose every idle child and refill. Called after a token rotation so warm children baked
            // with the benched token are replaced by ones carrying the new active token.
            rekey() {
              if (this.closed) return;
              for (const c of this.idle.splice(0)) {
                try {
                  c.kill('SIGKILL');
                } catch {}
              }
              this.refill();
            }
          
            close() {
              this.closed = true;
              for (const c of this.idle.splice(0)) {
                try {
                  c.kill('SIGKILL');
                } catch {}
              }
            }
          }
          
          // Run one warm turn on a leased child. Resolves with the assistant text; rejects on timeout or
          // a dead child so the caller can fall back to one-shot.
          function runWarmTurn(child, text, { timeoutMs = DEFAULTS.runTimeoutMs } = {}) {
            return new Promise((resolve, reject) => {
              let settled = false;
              let out = '';
              const dispose = () => {
                try {
                  child.kill('SIGKILL');
                } catch {}
              };
              const finish = (fn, arg) => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                dispose();
                fn(arg);
              };
              const timer = setTimeout(() => finish(reject, new Error('warm-turn-timeout')), timeoutMs);
          
              if (!child || !child.stdin || child.stdin.destroyed) {
                return finish(reject, new Error('child-unavailable'));
              }
              child.stdout.on('data', (d) => {
                out += d;
              });
              child.stdout.on('end', () => {
                const events = [];
                for (const line of out.split('\n')) {
                  const t = line.trim();
                  if (!t) continue;
                  try {
                    events.push(JSON.parse(t));
                  } catch {}
                }
                const text = extractResult(events);
                // An empty result is NOT a success: resolving '' would let ChatGateway return an empty
                // AIMessage that LangChain treats as success, so with_fallbacks never fires and the parser
                // throws with no Gemini/safe-default behind it. Reject so the request falls back (Binyan).
                if (!text) return finish(reject, new Error('empty-result'));
                finish(resolve, text);
              });
              child.on('error', (e) => finish(reject, e));
              // Resolve on stdout 'end'; 'close' (fires after stdio fully drains, unlike 'exit') only
              // guards a child that closed without flushing a result, so a good turn is never rejected by
              // an early exit event (council, Binyan).
              child.on('close', (code) => {
                if (!settled) finish(reject, new Error('child-close-' + code));
              });
              try {
                child.stdin.write(userTurnLine(text));
                child.stdin.end();
              } catch (e) {
                finish(reject, e);
              }
            });
          }
          
          // One-shot fallback: the wal-parse path. Cold (~6-8s) but reliable when the pool is unavailable.
          function runOneShot(text, { claudeBin, cwd, token, timeoutMs = DEFAULTS.oneShotTimeoutMs } = {}) {
            return new Promise((resolve, reject) => {
              let settled = false;
              let out = '';
              const child = spawn(
                claudeBin || process.env.CLAUDE_BIN || 'claude',
                ['-p', text, '--output-format', 'json', '--max-turns', '1', ...SAFE_ARGS],
                { cwd: cwd || '/alloc/data', stdio: ['ignore', 'pipe', 'ignore'], env: childSpawnEnv(process.env, token || null) }
              );
              const timer = setTimeout(() => {
                if (settled) return;
                settled = true;
                try {
                  child.kill('SIGKILL');
                } catch {}
                reject(new Error('one-shot-timeout'));
              }, timeoutMs);
              child.on('error', (e) => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                reject(e);
              });
              child.stdout.on('data', (d) => {
                out += d;
              });
              child.on('close', () => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                try {
                  const j = JSON.parse(out);
                  resolve(String(j.result ?? ''));
                } catch (e) {
                  reject(new Error('one-shot-parse: ' + (e && e.message)));
                }
              });
            });
          }
          
          // ── the request core (exported for the test) ────────────────────────────────
          
          function errorBody(code, message) {
            return JSON.stringify({ ok: false, error: { code, message: String(message).slice(0, 300) } });
          }
          
          // One attempt: lease a warm child, fall back to one-shot (carrying the active token). Returns the
          // assistant text; the HTTP layer shapes {ok, text|json}.
          async function runOnce(pool, combined, opts = {}) {
            const oneShotFn = opts.oneShotFn || runOneShot;
            const child = pool.lease();
            if (child) {
              try {
                const text = await runWarmTurn(child, combined, opts.warm);
                return { text, path: 'warm' };
              } catch {
                // fall through to one-shot
              }
            }
            const token = opts.tokenPool ? opts.tokenPool.active() : undefined;
            const text = await oneShotFn(combined, {
              claudeBin: pool.claudeBin,
              cwd: pool.cwd,
              token,
              ...(opts.oneShot || {}),
            });
            return { text, path: 'one-shot' };
          }
          
          // Resolve one /run with subscription-token rotation. On a "usage limit reached" turn, bench the
          // current account, re-key the warm pool, and retry on the next healthy token. When every token is
          // at its limit, throw the honest all-exhausted message (the HTTP layer returns it as model-error).
          // With no pool, or a single token, it is one plain attempt (unchanged behavior).
          async function resolveRun(pool, { system, prompt }, opts = {}) {
            const combined = (system ? system + '\n\n' : '') + prompt;
            const tokenPool = opts.tokenPool;
            if (!tokenPool || tokenPool.size <= 1) {
              return runOnce(pool, combined, opts);
            }
            for (let i = 0; i < tokenPool.size; i++) {
              const current = tokenPool.active();
              if (!current) break; // all benched
              const { text, path } = await runOnce(pool, combined, opts);
              const ex = detectExhaustion(text);
              if (!ex.exhausted) return { text, path };
              tokenPool.bench(current, ex.resetAt || cooldownReset());
              pool.rekey();
            }
            throw new Error(allExhaustedMessage(tokenPool.earliestReset()));
          }
          
          function makeHandler(pool, secret, runOpts = {}) {
            return function handler(req, res) {
              if (req.method === 'GET' && req.url === '/health') {
                res.writeHead(200, { 'content-type': 'application/json' });
                const tp = runOpts.tokenPool;
                res.end(
                  JSON.stringify({
                    ok: true,
                    svc: 'beans-ai',
                    pool: { ready: pool.ready, target: pool.target },
                    backend: 'claude-subscription',
                    tokens: tp ? { count: tp.size, allBenched: tp.allBenched(), accounts: tp.statuses() } : null,
                  })
                );
                return;
              }
              if (req.method === 'POST' && req.url === '/run') {
                if (!bearerOk(req.headers['authorization'], secret)) {
                  res.writeHead(401, { 'content-type': 'application/json' });
                  res.end(errorBody('unauthorized', 'missing or bad bearer token'));
                  return;
                }
                let body = '';
                let tooBig = false;
                req.on('data', (d) => {
                  body += d;
                  if (Buffer.byteLength(body) > DEFAULTS.maxPromptBytes && !tooBig) {
                    // Answer with the named-error envelope instead of destroying the socket (Binyan).
                    tooBig = true;
                    res.writeHead(413, { 'content-type': 'application/json' });
                    res.end(errorBody('too-large', 'request body exceeds limit'));
                    req.destroy();
                  }
                });
                req.on('end', async () => {
                  if (tooBig) return; // already answered with the 413 envelope
                  let payload;
                  try {
                    payload = JSON.parse(body || '{}');
                  } catch {
                    res.writeHead(400, { 'content-type': 'application/json' });
                    res.end(errorBody('bad-json', 'request body is not valid JSON'));
                    return;
                  }
                  const prompt = (payload.prompt ?? '').toString();
                  const system = (payload.system ?? '').toString();
                  const wantJson = payload.json_schema != null;
                  if (!prompt.trim()) {
                    res.writeHead(400, { 'content-type': 'application/json' });
                    res.end(errorBody('empty-prompt', 'prompt is required'));
                    return;
                  }
                  try {
                    const { text, path } = await resolveRun(pool, { system, prompt }, runOpts);
                    const out = { ok: true, path };
                    if (wantJson) {
                      try {
                        out.json = carveJson(text);
                      } catch (e) {
                        res.writeHead(502, { 'content-type': 'application/json' });
                        res.end(errorBody('no-json', (e && e.message) || 'model returned no json'));
                        return;
                      }
                    } else {
                      out.text = text;
                    }
                    res.writeHead(200, { 'content-type': 'application/json' });
                    res.end(JSON.stringify(out));
                  } catch (e) {
                    res.writeHead(502, { 'content-type': 'application/json' });
                    res.end(errorBody('model-error', (e && e.message) || e));
                  }
                });
                return;
              }
              res.writeHead(404, { 'content-type': 'application/json' });
              res.end(errorBody('not-found', req.url));
            };
          }
          
          // ── server factory ──────────────────────────────────────────────────────────
          
          export function createGateway(opts = {}) {
            const secret = opts.secret ?? process.env.BEANS_AI_SHARED_SECRET;
            if (!secret) throw new Error('BEANS_AI_SHARED_SECRET required');
            // Subscription-token pool: injected tokens (tests) or parsed from env (the Nomad Variable
            // carries one primary plus optional backups). The ChildPool spawns each child with the active
            // token; resolveRun rotates on a usage-limit turn.
            const tokenPool = opts.tokenPool || new TokenPool(opts.tokens || parseTokens());
            const pool = new ChildPool({ ...opts, tokenFn: () => tokenPool.active() });
            pool.refill();
            const server = http.createServer(
              makeHandler(pool, secret, { oneShotFn: opts.oneShotFn, warm: opts.warm, oneShot: opts.oneShot, tokenPool })
            );
            const origClose = server.close.bind(server);
            server.close = (cb) => {
              pool.close();
              return origClose(cb);
            };
            server._pool = pool; // test hook
            server._tokenPool = tokenPool; // test hook
            return server;
          }
          
          // Exported internals for unit tests.
          export { ChildPool, runWarmTurn, runOneShot, resolveRun, extractResult, carveJson, userTurnLine, makeHandler };
          
          // Start when run directly (the Nomad entrypoint does `node /local/gateway.mjs`).
          const isMain = (() => {
            try {
              return import.meta.url === 'file://' + process.argv[1] || (process.argv[1] || '').endsWith('gateway.mjs');
            } catch {
              return false;
            }
          })();
          
          if (isMain) {
            const port = process.env.NOMAD_PORT_http || process.env.PORT || 8080;
            const server = createGateway({ cwd: process.env.ALLOC_DATA || '/alloc/data' });
            server.listen(port, () => console.log('[beans-ai] warm gateway http on ' + port));
          }
        EOJS
      }

      # Sibling module imported by gateway.mjs (subscription-token rotation). Shipped next to
      # gateway.mjs so `import './token-pool.mjs'` resolves on the box. Embedded by build-hcl.mjs.
      template {
        destination = "local/token-pool.mjs"
        perms       = "0644"
        data        = <<-EOJS
          // deploy/token-pool.mjs — in-memory Claude subscription token rotation for the beans-ai gateway.
          //
          // The gateway authenticates headless with CLAUDE_CODE_OAUTH_TOKEN (a subscription token, not an
          // API key). One subscription hits its usage window and the gateway goes silent until it resets.
          // This holds several tokens (one per account: a primary plus one or two backups) and rotates to
          // the next healthy one the instant a turn comes back "usage limit reached".
          //
          // SIMPLE variant (Dario's call, 2026-10-19): the token list lives in the Nomad Variable alongside
          // the bearer, and benching is in-memory. No database. On a restart the benched state resets, which
          // self-corrects: a still-exhausted token just re-benches on its next use (cheap). The richer
          // Neon-backed store Quinn uses (quinn-discord/token-pool.mjs + db.mjs) is the promotion path if
          // beans ever needs benched state to survive restarts or be shared; the pure detection below is
          // lifted from that module unchanged so the two stay in sync.
          //
          // A subscription token can only be minted by an interactive `claude setup-token` browser login;
          // it can never be generated. Dario seeds the list into the Nomad Variable.

          const DEFAULT_COOLDOWN_MIN = Number(process.env.BEANS_TOKEN_COOLDOWN_MIN) || 60;

          // ── Pure detection (lifted from quinn-discord/token-pool.mjs, kept identical) ──────────────
          // Decide if `text` (a claude run's output) is a subscription-limit failure, and pull the reset
          // time if present. The machine form is "usage limit reached|<unix-epoch>"; human phrasings carry
          // no parseable reset.
          export function detectExhaustion(text) {
            if (!text) return { exhausted: false, resetAt: null };
            const t = String(text);
            const epochM = t.match(/usage limit reached\s*[|:]\s*(\d{10,13})/i);
            if (epochM) {
              let n = Number(epochM[1]);
              if (n < 1e12) n *= 1000; // seconds -> ms
              const d = new Date(n);
              return { exhausted: true, resetAt: isNaN(d.getTime()) ? null : d };
            }
            const SIGNATURES = [
              /usage limit reached/i,
              /reached your (?:usage )?limit/i,
              /\b5-hour limit reached\b/i,
              /\bweekly limit reached\b/i,
              /\blimit will reset\b/i,
              /you'?ve (?:hit|reached) your [^.\n]*limit/i,
            ];
            if (SIGNATURES.some((re) => re.test(t))) return { exhausted: true, resetAt: null };
            return { exhausted: false, resetAt: null };
          }

          export function cooldownReset(now = new Date()) {
            return new Date(now.getTime() + DEFAULT_COOLDOWN_MIN * 60 * 1000);
          }

          export function allExhaustedMessage(reset) {
            const when = reset ? ` La primera se resetea alrededor de ${new Date(reset).toISOString()}.` : '';
            return `Todas las cuentas de Beans estan en su limite de uso.${when} Agrega una cuenta o espera el reset.`;
          }

          // Parse the token list from env. Accepts CLAUDE_CODE_OAUTH_TOKENS as a JSON array OR a
          // newline/comma-separated list, and the single CLAUDE_CODE_OAUTH_TOKEN for back-compat. Order is
          // preserved (primary first), empties dropped, duplicates removed.
          export function parseTokens(env = process.env) {
            const out = [];
            const push = (v) => {
              const s = String(v || '').trim();
              if (s && !out.includes(s)) out.push(s);
            };
            const many = (env.CLAUDE_CODE_OAUTH_TOKENS || '').trim();
            if (many) {
              if (many.startsWith('[')) {
                try { JSON.parse(many).forEach(push); } catch { /* fall through to split */ }
              }
              if (!out.length) many.split(/[\n,]/).forEach(push);
            }
            push(env.CLAUDE_CODE_OAUTH_TOKEN);
            // Numbered back-compat: CLAUDE_CODE_OAUTH_TOKEN_2, _3, ...
            for (let i = 2; i <= 9; i++) push(env['CLAUDE_CODE_OAUTH_TOKEN_' + i]);
            return out;
          }

          function tail(token) {
            return '…' + String(token).slice(-6);
          }

          // In-memory pool: a list of tokens, each benchable until a reset time.
          export class TokenPool {
            constructor(tokens = []) {
              this.entries = tokens.map((token, i) => ({ token, exhaustedUntil: null, label: 'acct-' + (i + 1) }));
            }

            get size() {
              return this.entries.length;
            }

            _healthy(now) {
              const t = now instanceof Date ? now.getTime() : now;
              return this.entries.filter((e) => !e.exhaustedUntil || e.exhaustedUntil.getTime() <= t);
            }

            // The token to spawn with: the first healthy one, or null when the pool is empty/all-benched.
            active(now = new Date()) {
              const h = this._healthy(now);
              return h.length ? h[0].token : null;
            }

            bench(token, resetAt) {
              const e = this.entries.find((x) => x.token === token);
              if (e) e.exhaustedUntil = resetAt instanceof Date ? resetAt : cooldownReset();
            }

            allBenched(now = new Date()) {
              return this.size > 0 && this._healthy(now).length === 0;
            }

            earliestReset() {
              const times = this.entries.map((e) => e.exhaustedUntil).filter(Boolean).map((d) => d.getTime());
              return times.length ? new Date(Math.min(...times)) : null;
            }

            // Masked board for /health; never exposes a token.
            statuses(now = new Date()) {
              const t = now.getTime();
              return this.entries.map((e, i) => ({
                label: e.label,
                tail: tail(e.token),
                active: i === 0 ? undefined : undefined, // active is derived; omit to avoid implying order
                benched: !!(e.exhaustedUntil && e.exhaustedUntil.getTime() > t),
                until: e.exhaustedUntil ? e.exhaustedUntil.toISOString() : null,
              }));
            }
          }

          // The env a spawned claude child should carry: the active token overrides whatever is ambient, so
          // rotation takes effect on the next spawn. Pure so the wiring is unit-testable without a binary.
          export function childSpawnEnv(baseEnv, activeToken) {
            if (!activeToken) return baseEnv;
            return { ...baseEnv, CLAUDE_CODE_OAUTH_TOKEN: activeToken };
          }
        EOJS
      }

      service {
        name     = "beans-ai"
        port     = "http"
        provider = "consul"
        tags = [
          "traefik.enable=true",
          "traefik.http.routers.beans-ai.rule=Host(`beans-ai.mdlautomations.duckdns.org`)",
          "traefik.http.routers.beans-ai.entrypoints=websecure",
          "traefik.http.routers.beans-ai.tls.certresolver=le",
        ]
        check {
          type     = "http"
          path     = "/health"
          interval = "20s"
          timeout  = "5s"
        }
      }

      resources {
        cpu        = 1200
        memory     = 768
        memory_max = 2560
      }
    }
  }
}
