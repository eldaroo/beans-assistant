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
        # NET_ADMIN lets the entrypoint apply the network egress firewall (spec 010 M5, T-026,
        # AC-T7): a deny-all-except control that is the LOAD-BEARING egress guard, with the in-code
        # egress-guard.mjs as the second layer. Without this cap the firewall step fails closed.
        cap_add = ["NET_ADMIN"]
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
          INTERNAL_SERVICE_TOKEN={{ .INTERNAL_SERVICE_TOKEN }}
          BEANS_OPS_URL={{ .BEANS_OPS_URL }}
          BEANS_TENANT_PHONE={{ .BEANS_TENANT_PHONE }}
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
          log "isolation OK: no org-keyring value; env carries the model token(s), the bearer, and the beans internal-op wiring"
          log "toolchain: node $(node --version) · $(claude --version 2>/dev/null | head -1)"

          # Pin the Claude CLI to a version where MCP servers connect BEFORE the first turn (2.1.304).
          # The image's 2.1.215 connects MCP asynchronously, so the beans tools are not callable at
          # turn start and the agent cannot use them (verified on the box). Skip if already pinned.
          WANT_CLAUDE="2.1.304"
          HAVE_CLAUDE="$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
          if [ "$${HAVE_CLAUDE}" != "$${WANT_CLAUDE}" ]; then
            log "pinning Claude CLI $${HAVE_CLAUDE} -> $${WANT_CLAUDE}"
            npm i -g @anthropic-ai/claude-code@$${WANT_CLAUDE} >/dev/null 2>&1 || { log "FATAL: claude pin failed"; exit 1; }
            log "pinned: $(claude --version 2>/dev/null | head -1)"
          fi

          # ── Network egress firewall (spec 010 M5, T-026, AC-T7) ─────────────────────────────
          # The LOAD-BEARING egress control: default-DROP on OUTPUT, allow only loopback, already-
          # established flows, DNS to the box's resolvers, and TCP/443 to the resolved IPs of the
          # Next internal-ops host (BEANS_OPS_URL) and api.anthropic.com. The in-code
          # egress-guard.mjs is the SECOND layer (it cannot stop a compromised dependency calling
          # fetch directly; this can). It runs AFTER the Claude-CLI pin on purpose (council: Tamir
          # HIGH): the pin's `npm i` reaches registry.npmjs.org, which is NOT on the allowlist, so a
          # firewall applied before the pin would fail-closed and brick the boot. By here the only
          # egress the running gateway needs is the ops host + Anthropic. Fail CLOSED: if the
          # firewall cannot be applied the box must not serve, because an un-firewalled tool-use box
          # is the exact exfiltration surface spec 007 forbids. BEANS_EGRESS_FIREWALL=0 is the
          # documented deploy escape hatch (relies on the in-code guard only) for a host where
          # NET_ADMIN or nft is unavailable; Dario sets it explicitly at deploy (#273), never default.
          if [ "$${BEANS_EGRESS_FIREWALL:-1}" != "0" ]; then
            OPS_HOST="$(node -e 'try{process.stdout.write(new URL(process.env.BEANS_OPS_URL).hostname)}catch(e){process.exit(3)}')" || { log "FATAL: BEANS_OPS_URL invalid, cannot firewall"; exit 1; }
            log "egress firewall: default-drop, allow DNS + 443 to $${OPS_HOST} + api.anthropic.com"
            command -v nft >/dev/null 2>&1 || { log "FATAL: nft absent and BEANS_EGRESS_FIREWALL!=0 (fail closed)"; exit 1; }
            resolve_ips() { getent ahosts "$1" 2>/dev/null | awk '{print $1}' | sort -u; }
            ALLOW_IPS="$(resolve_ips "$${OPS_HOST}"; resolve_ips api.anthropic.com)"
            [ -n "$${ALLOW_IPS}" ] || { log "FATAL: could not resolve any allowed egress IP (fail closed)"; exit 1; }
            # External (non-loopback) resolvers to pin DNS to (council: Tamir/Binyan MED — DNS-to-any
            # is a covert exfil channel). Loopback resolvers (systemd-resolved 127.0.0.53, Docker
            # embedded 127.0.0.11) are already covered by `oif lo accept`. SAFE FALLBACK: if no
            # external resolver is found, leave 53 open rather than risk bricking DNS (the firewall
            # is deploy-validated, #273, and must never fail-closed on a resolver topology we did not
            # test). The tighter the better, but availability wins over a NIT-grade channel here.
            RESOLVERS="$(awk '/^nameserver/ && $2 !~ /^127\./ && $2 !~ /:/ {print $2}' /etc/resolv.conf 2>/dev/null | sort -u)"
            nft flush ruleset 2>/dev/null || true
            nft add table inet beans_egress
            nft 'add chain inet beans_egress output { type filter hook output priority 0 ; policy drop ; }'
            nft add rule inet beans_egress output oif lo accept
            nft add rule inet beans_egress output ct state established,related accept
            if [ -n "$${RESOLVERS}" ]; then
              for r in $${RESOLVERS}; do
                nft add rule inet beans_egress output ip daddr "$${r}" udp dport 53 accept
                nft add rule inet beans_egress output ip daddr "$${r}" tcp dport 53 accept
              done
              log "egress firewall: DNS pinned to resolvers [$$(echo $${RESOLVERS} | tr '\n' ' ')]"
            else
              nft add rule inet beans_egress output udp dport 53 accept
              nft add rule inet beans_egress output tcp dport 53 accept
              log "egress firewall: no external resolver in resolv.conf; DNS left open (loopback resolver assumed)"
            fi
            for ip in $${ALLOW_IPS}; do
              case "$${ip}" in *:*) continue;; esac   # v4 allowlist; the box reaches both hosts over v4
              nft add rule inet beans_egress output ip daddr "$${ip}" tcp dport 443 accept
            done
            log "egress firewall applied: allow 443 -> [$$(echo $${ALLOW_IPS} | tr '\n' ' ')]"
          else
            log "egress firewall DISABLED by BEANS_EGRESS_FIREWALL=0; relying on the in-code guard only"
          fi

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
          import { verifyToolPosture } from './tool-posture.mjs';
          import { verifyEgressConfig } from './egress-guard.mjs';
          
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
          
          // ── native tool-use mode (spec 007) ──────────────────────────────────────────
          // The agent turn runs ONE fresh child per request with the narrow beans MCP tools allowlisted and
          // every other tool disallowed. --allowedTools is an auto-APPROVE grant, not an exclusive allowlist
          // (spike 2026-10-19), so the real guard is the boot posture self-check (verifyToolMode) that probes
          // the actual callable set and refuses to serve unless it is exactly mcp__beans__*. This denylist is
          // defense-in-depth; the self-check catches anything a new claude version adds that it misses.
          // The complete built-in set observed on the deployed claude (2.1.215, quinn-brain image). The boot
          // self-check (verifyToolMode) is the backstop: if a future version adds a tool this misses, it fails
          // closed. Keep this a superset so the box boots clean.
          const TOOL_MODE_DISALLOWED = Array.from(new Set([
            ...DISALLOWED_TOOLS, // Bash, BashOutput, KillShell, Edit, Write, Read, NotebookEdit, WebFetch, WebSearch, Task, Glob, Grep
            'TodoWrite', 'Monitor', 'Workflow', 'SendMessage', 'RemoteTrigger',
            'CronCreate', 'CronDelete', 'CronList', 'DesignSync', 'EnterWorktree', 'ExitWorktree',
            'ListAgents', 'PushNotification', 'ScheduleWakeup', 'ReportFindings', 'ToolSearch',
            'Skill', 'EndConversation', 'ReadMcpResourceTool', 'ListMcpResourcesTool',
            // The 2.1.215 Task family and the onboarding helper seen leaking in the first prod boot.
            'TaskCreate', 'TaskGet', 'TaskList', 'TaskOutput', 'TaskStop', 'TaskUpdate', 'ShareOnboardingGuide',
            // Present on the pinned 2.1.304 (caught by the boot self-check on the second prod boot).
            'PublishPlugin',
          ]));
          
          const BEANS_MCP_CONFIG = process.env.BEANS_MCP_CONFIG || '/local/mcp-beans.json';
          const AGENT_MAX_TURNS = Number(process.env.BEANS_AGENT_MAX_TURNS) || 6;
          // A native-tool agent turn is multi-hop (cold child start + MCP connect + a tool roundtrip to the
          // internal API + model generation), so it needs far more headroom than a tool-free classification
          // turn. Keep it under the client's call_agent timeout so the gateway returns a result, not a cutoff.
          const AGENT_TURN_TIMEOUT = Number(process.env.BEANS_AGENT_TIMEOUT_MS) || 120000;
          
          // The tool-mode flags, shared by the real turn and the boot self-check so they probe what runs.
          export function agentFlags(mcpConfig = BEANS_MCP_CONFIG) {
            return [
              '--allowedTools', 'mcp__beans__*',
              '--disallowedTools', ...TOOL_MODE_DISALLOWED,
              '--mcp-config', mcpConfig,
              '--strict-mcp-config',
            ];
          }
          
          // The COMPLETE production argv for one agent turn (spec 010 M5, T-025, AC-T8). The single source
          // of truth for how the real child is spawned, so the boot posture self-check validates the exact
          // tool governance that runs — not a hand-kept copy that could drift. runAgentTurn calls this; the
          // posture self-check derives its probe from the same TOOL_MODE_DISALLOWED + mcp__beans__* flags.
          // --dangerously-skip-permissions is NEVER here: in headless -p with no TTY, that absence is what
          // keeps a tool call auto-DENIED unless it is an allowlisted MCP tool (the whole safety model).
          export function buildAgentArgs({ system, maxTurns = AGENT_MAX_TURNS, mcpConfig = BEANS_MCP_CONFIG } = {}) {
            return [
              '-p',
              '--input-format', 'stream-json',
              '--output-format', 'stream-json',
              '--verbose',
              '--max-turns', String(maxTurns),
              ...(system ? ['--append-system-prompt', system] : []),
              ...agentFlags(mcpConfig),
            ];
          }
          
          // True iff an argv asks to skip permissions. The production argv must NEVER satisfy this (AC-T8);
          // a test asserts it on buildAgentArgs so a future edit that adds the flag fails loudly.
          export function argvSkipsPermissions(argv) {
            return (argv || []).some((a) => String(a) === '--dangerously-skip-permissions');
          }
          
          // Boot posture self-check: probe the real claude with the production tool-mode flags and confirm
          // the callable set is exactly the beans MCP tools. Fail closed (the entrypoint exits non-zero).
          export async function verifyToolMode({ claudeBin, cwd, mcpConfig = BEANS_MCP_CONFIG, timeoutMs } = {}) {
            return verifyToolPosture({
              claudeBin,
              cwd,
              mcpConfig,
              allowedTools: ['mcp__beans__*'],
              disallowedTools: TOOL_MODE_DISALLOWED,
              timeoutMs,
            });
          }
          
          // Run ONE native tool-use turn on a fresh child (no warm pool: each request gets a disposed child
          // with the current pool token). Resolves the assistant's final text; rejects on timeout/dead child.
          // The out-of-band facts pinned into the agent child's env (spec 010 M3, T-015). Only non-empty
          // values are set, so a read-only turn (no flow/owner) spawns exactly as before. Exported for the
          // gateway test. None of these is ever a model prompt input or a tool arg.
          export function agentChildEnv({ turnNonce, flowNonce, owner } = {}) {
            const extra = {};
            if (turnNonce) extra.BEANS_TURN_NONCE = turnNonce;
            if (flowNonce) extra.BEANS_FLOW_NONCE = flowNonce;
            if (owner) extra.BEANS_OWNER = owner;
            return Object.keys(extra).length ? extra : null;
          }
          
          function runAgentTurn(userText, { claudeBin, cwd, token, system, turnNonce, flowNonce, owner, mcpConfig = BEANS_MCP_CONFIG, maxTurns = AGENT_MAX_TURNS, timeoutMs = AGENT_TURN_TIMEOUT, spawnChild } = {}) {
            return new Promise((resolve, reject) => {
              let settled = false;
              let out = '';
              const args = buildAgentArgs({ system, maxTurns, mcpConfig });
              let child;
              try {
                child = spawnChild
                  ? spawnChild(args, token)
                  : spawn(claudeBin || process.env.CLAUDE_BIN || 'claude', args, {
                      cwd: cwd || '/alloc/data',
                      stdio: ['pipe', 'pipe', 'ignore'],
                      // Pin the per-turn nonce, the flow nonce, and the authenticated owner into the child
                      // env (out of band, like the tenant) so the MCP server stamps the turn nonce on any
                      // staged write (spec 007 correlation) and sends the flow nonce + owner on a
                      // write-preview call so the internal endpoint grounds against operator_turns keyed
                      // by (owner, flowNonce) (spec 010 M3, T-015, D-061). The MODEL never sees these: they
                      // live in the child env, never in the prompt or a tool arg.
                      env: childSpawnEnv(process.env, token || null, agentChildEnv({ turnNonce, flowNonce, owner })),
                    });
              } catch (e) {
                return reject(e);
              }
              const dispose = () => { try { child.kill('SIGKILL'); } catch {} };
              const finish = (fn, arg) => { if (settled) return; settled = true; clearTimeout(timer); dispose(); fn(arg); };
              const timer = setTimeout(() => finish(reject, new Error('agent-turn-timeout')), timeoutMs);
              if (!child || !child.stdin) return finish(reject, new Error('child-unavailable'));
              child.stdout.on('data', (d) => { out += d; });
              child.stdout.on('end', () => {
                const events = [];
                for (const line of out.split('\n')) {
                  const t = line.trim();
                  if (!t) continue;
                  try { events.push(JSON.parse(t)); } catch {}
                }
                const text = extractResult(events);
                if (!text) return finish(reject, new Error('empty-result'));
                finish(resolve, text);
              });
              child.on('error', (e) => finish(reject, e));
              child.on('close', (code) => { if (!settled) finish(reject, new Error('child-close-' + code)); });
              try {
                child.stdin.write(userTurnLine(userText));
                child.stdin.end();
              } catch (e) {
                finish(reject, e);
              }
            });
          }
          
          // Resolve one /run-agent with token rotation: on a usage-limit turn, bench + rotate + retry.
          async function resolveAgent(userText, opts = {}) {
            const tokenPool = opts.tokenPool;
            const attempts = tokenPool && tokenPool.size > 1 ? tokenPool.size : 1;
            for (let i = 0; i < attempts; i++) {
              const current = tokenPool ? tokenPool.active() : undefined;
              if (tokenPool && tokenPool.size > 1 && !current) break;
              const text = await (opts.agentFn || runAgentTurn)(userText, { ...opts, token: current });
              if (tokenPool && tokenPool.size > 1) {
                const ex = detectExhaustion(text);
                if (ex.exhausted) {
                  tokenPool.bench(current, ex.resetAt || cooldownReset());
                  continue;
                }
              }
              return { text, path: 'agent' };
            }
            throw new Error(allExhaustedMessage(tokenPool ? tokenPool.earliestReset() : null));
          }
          
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
              if (req.method === 'POST' && req.url === '/run-agent') {
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
                    tooBig = true;
                    res.writeHead(413, { 'content-type': 'application/json' });
                    res.end(errorBody('too-large', 'request body exceeds limit'));
                    req.destroy();
                  }
                });
                req.on('end', async () => {
                  if (tooBig) return;
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
                  const turnNonce = (payload.turn_nonce ?? '').toString() || null;
                  // The flow nonce + owner ride in the request envelope out of band (spec 010 M3, T-015);
                  // the route sends them, the gateway injects them into the child env, the model never
                  // sees them. They key the operator_turns grounding on a write-preview call (D-061).
                  const flowNonce = (payload.flow_nonce ?? '').toString() || null;
                  const owner = (payload.owner ?? '').toString() || null;
                  if (!prompt.trim()) {
                    res.writeHead(400, { 'content-type': 'application/json' });
                    res.end(errorBody('empty-prompt', 'prompt is required'));
                    return;
                  }
                  try {
                    const { text, path } = await resolveAgent(prompt, {
                      tokenPool: runOpts.tokenPool,
                      claudeBin: pool.claudeBin,
                      cwd: pool.cwd,
                      agentFn: runOpts.agentFn,
                      system,
                      turnNonce,
                      flowNonce,
                      owner,
                    });
                    res.writeHead(200, { 'content-type': 'application/json' });
                    res.end(JSON.stringify({ ok: true, path, text }));
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
              makeHandler(pool, secret, { oneShotFn: opts.oneShotFn, warm: opts.warm, oneShot: opts.oneShot, tokenPool, agentFn: opts.agentFn })
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
          export { ChildPool, runWarmTurn, runOneShot, resolveRun, resolveAgent, runAgentTurn, extractResult, carveJson, userTurnLine, makeHandler };
          
          // Start when run directly (the Nomad entrypoint does `node /local/gateway.mjs`).
          const isMain = (() => {
            try {
              return import.meta.url === 'file://' + process.argv[1] || (process.argv[1] || '').endsWith('gateway.mjs');
            } catch {
              return false;
            }
          })();
          
          if (isMain) {
            (async () => {
              const port = process.env.NOMAD_PORT_http || process.env.PORT || 8080;
              const cwd = process.env.ALLOC_DATA || '/alloc/data';
              // Boot tool-posture self-check (D-035): refuse to serve the agent path unless the real claude's
              // callable set is exactly mcp__beans__*. Skippable with BEANS_TOOL_MODE=0 for a tool-free box.
              if (process.env.BEANS_TOOL_MODE !== '0') {
                try {
                  const posture = await verifyToolMode({ cwd });
                  if (!posture.ok) {
                    console.error('[beans-ai] FATAL tool-posture self-check failed; offending=' + JSON.stringify(posture.offending) + ' callable=' + JSON.stringify(posture.callable));
                    process.exit(1);
                  }
                  console.log('[beans-ai] tool-posture OK: callable=' + JSON.stringify(posture.callable));
                } catch (e) {
                  console.error('[beans-ai] FATAL tool-posture probe error: ' + (e && e.message));
                  process.exit(1);
                }
                // Boot egress self-check (spec 007 M4, AC12): the box must only be able to name the ops
                // API and Anthropic as egress. Fail closed on a missing/misconfigured allowlist. The
                // network-level firewall (Nomad job) is the hard enforcement; this is the in-code backstop.
                const egress = verifyEgressConfig();
                if (!egress.ok) {
                  console.error('[beans-ai] FATAL egress config check failed; reason=' + egress.reason + ' allow=' + JSON.stringify(egress.allowlist));
                  process.exit(1);
                }
                console.log('[beans-ai] egress OK: allow=' + JSON.stringify(egress.allowlist));
              }
              const server = createGateway({ cwd });
              server.listen(port, () => console.log('[beans-ai] warm gateway http on ' + port));
            })();
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
            const when = reset ? ` La primera se resetea alrededor de $${new Date(reset).toISOString()}.` : '';
            return `Todas las cuentas de Beans estan en su limite de uso.$${when} Agrega una cuenta o espera el reset.`;
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
          export function childSpawnEnv(baseEnv, activeToken, extra = null) {
            if (!activeToken && !extra) return baseEnv;
            const env = { ...baseEnv };
            if (activeToken) env.CLAUDE_CODE_OAUTH_TOKEN = activeToken;
            if (extra) Object.assign(env, extra);
            return env;
          }
        EOJS
      }

      # Boot tool-posture self-check, imported by gateway.mjs (spec 007 D-035). Embedded by build-hcl.mjs.
      template {
        destination = "local/tool-posture.mjs"
        perms       = "0644"
        data        = <<-EOJS
          // Boot tool-posture self-check for the native-tool-use gateway (spec 007, D-035 corrected).
          //
          // WHY THIS EXISTS (spike finding, 2026-10-19): `--allowedTools mcp__beans__*` is an
          // auto-APPROVE grant, NOT an exclusive allowlist. In headless `-p` with no TTY, an MCP
          // tool on the allowlist auto-approves and runs WITHOUT --dangerously-skip-permissions
          // (good, the approach works), but every OTHER tool Claude Code loads stays callable unless
          // it is on `--disallowedTools`. The spike proved a model could reach `Monitor` (a
          // shell-capable built-in) that a hand-maintained denylist had missed. A static denylist is
          // fragile: a future claude version adds a tool and the list silently misses it.
          //
          // The robust control is a POSITIVE-IDENTITY check on the actually-callable tool set: at boot,
          // probe the real `claude` with the intended argv, read the INIT `tools` array it reports, and
          // refuse to serve unless that set is exactly the beans MCP tools and nothing else. Fail closed.
          import { spawn } from 'node:child_process';
          
          // Tools the gateway intends to expose. Only names matching this prefix may be callable.
          export const ALLOWED_MCP_PREFIX = 'mcp__beans__';
          
          // Probe the real claude binary with the gateway's intended argv and return the INIT tool set.
          // We only need the first `{"type":"system","subtype":"init","tools":[...]}` line, so we read
          // stdout until that event arrives, then kill the child. No model turn is spent.
          export function probeCallableTools({
            claudeBin = process.env.CLAUDE_BIN || 'claude',
            mcpConfig,
            allowedTools = [ALLOWED_MCP_PREFIX + '*'],
            disallowedTools = [],
            cwd,
            timeoutMs = 20000,
          } = {}) {
            return new Promise((resolve, reject) => {
              const args = [
                '-p', 'ok',
                '--output-format', 'stream-json',
                '--verbose',
                '--max-turns', '1',
                '--allowedTools', ...allowedTools,
              ];
              if (disallowedTools.length) args.push('--disallowedTools', ...disallowedTools);
              if (mcpConfig) args.push('--mcp-config', mcpConfig, '--strict-mcp-config');
          
              let child;
              try {
                child = spawn(claudeBin, args, { cwd, stdio: ['ignore', 'pipe', 'ignore'] });
              } catch (e) {
                reject(new Error('probe spawn failed: ' + e.message));
                return;
              }
          
              let buf = '';
              let settled = false;
              const done = (fn, v) => { if (settled) return; settled = true; clearTimeout(timer); try { child.kill(); } catch {} fn(v); };
              const timer = setTimeout(() => done(reject, new Error('probe timeout: no init event in ' + timeoutMs + 'ms')), timeoutMs);
          
              child.on('error', (e) => done(reject, new Error('probe error: ' + e.message)));
              child.stdout.setEncoding('utf8');
              child.stdout.on('data', (chunk) => {
                buf += chunk;
                let idx;
                while ((idx = buf.indexOf('\n')) >= 0) {
                  const line = buf.slice(0, idx).trim();
                  buf = buf.slice(idx + 1);
                  if (!line) continue;
                  let e;
                  try { e = JSON.parse(line); } catch { continue; }
                  if (e && e.type === 'system' && e.subtype === 'init' && Array.isArray(e.tools)) {
                    done(resolve, {
                      tools: e.tools.slice(),
                      mcpServers: Array.isArray(e.mcp_servers) ? e.mcp_servers.slice() : [],
                    });
                    return;
                  }
                }
              });
              child.on('exit', () => {
                if (!settled) done(reject, new Error('probe exited before init event'));
              });
            });
          }
          
          // Decide pass/fail from an init probe {tools, mcpServers} (a bare tools array is accepted too).
          //
          // SECURITY (the hard guarantee): every callable built-in must be disallowed, so the only tool a
          // hijacked model can reach is a beans MCP tool. That is `offending.length === 0`: no tool in the
          // init `tools` array falls outside the allowed MCP prefix.
          //
          // LIVENESS: the beans MCP server connects ASYNCHRONOUSLY. On claude 2.1.215 the init event fires
          // while it is still "pending", so its tools are NOT in the init snapshot yet (they become callable
          // mid-turn, verified live). Requiring beans tools in the init array would wrongly fail there, so
          // liveness is "beans is configured and not failed" (claude parsed the config and is connecting it),
          // not "its tools are already listed". The real end-to-end read is proven by the live loop.
          export function judgeToolPosture(probe, { allowedPrefix = ALLOWED_MCP_PREFIX } = {}) {
            const tools = Array.isArray(probe) ? probe : (probe && probe.tools) || [];
            const mcpServers = Array.isArray(probe) ? [] : (probe && probe.mcpServers) || [];
            const offending = tools.filter((t) => !String(t).startsWith(allowedPrefix));
            const beansTools = tools.filter((t) => String(t).startsWith(allowedPrefix));
            const beans = mcpServers.find((s) => s && s.name === 'beans');
            const beansConfigured = !!beans && beans.status !== 'failed' && beans.status !== 'error';
            return {
              ok: offending.length === 0 && beansConfigured,
              callable: tools,
              beansTools,
              offending,
              mcpServers,
              beansStatus: beans ? beans.status : 'absent',
            };
          }
          
          // Full self-check: probe the real claude and judge. Resolves the judge verdict object.
          export async function verifyToolPosture(opts = {}) {
            const probe = await probeCallableTools(opts);
            return judgeToolPosture(probe, opts);
          }
          
          // CLI entry: node tool-posture.mjs --mcp-config <path> [--disallow a b c]. Exit 0 on pass,
          // 1 on a leak (fail closed), 2 on a probe error. The gateway entrypoint calls this at boot.
          async function main(argv) {
            const get = (flag) => {
              const i = argv.indexOf(flag);
              if (i < 0) return undefined;
              const out = [];
              for (let j = i + 1; j < argv.length && !argv[j].startsWith('--'); j++) out.push(argv[j]);
              return out;
            };
            const mcpConfig = (get('--mcp-config') || [])[0];
            const disallowedTools = get('--disallow') || [];
            const allowedTools = get('--allow') || [ALLOWED_MCP_PREFIX + '*'];
            try {
              const r = await verifyToolPosture({ mcpConfig, disallowedTools, allowedTools });
              if (r.ok) {
                console.log('TOOL-POSTURE-OK callable=' + JSON.stringify(r.callable));
                process.exit(0);
              }
              console.error('TOOL-POSTURE-FAIL offending=' + JSON.stringify(r.offending) + ' callable=' + JSON.stringify(r.callable));
              process.exit(1);
            } catch (e) {
              console.error('TOOL-POSTURE-PROBE-ERROR ' + e.message);
              process.exit(2);
            }
          }
          
          // Run main only when invoked directly, not when imported.
          import { fileURLToPath } from 'node:url';
          if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
            main(process.argv.slice(2));
          }
        EOJS
      }

      # Boot egress allowlist self-check, imported by gateway.mjs (spec 007 M4, AC12). Embedded by build-hcl.mjs.
      template {
        destination = "local/egress-guard.mjs"
        perms       = "0644"
        data        = <<-EOJS
          // Egress allowlist for the native-tool-use gateway box (spec 007 M4, AC12).
          //
          // The box must only ever reach two places: the internal operation API (the ONLY place the
          // tools call) and Anthropic (the model). Anything else — a data-exfiltration callback a
          // hijacked model or a compromised dependency might attempt — must be refused. The hard,
          // network-level enforcement is the Nomad job's egress firewall (infra, deployed in M6); this
          // module is the application-level allowlist + a boot assertion that the allowlist is sane and
          // a guarded-fetch wrapper the outbound call paths use, so the control is testable and fails
          // closed in code as well as at the firewall.
          import process from 'node:process';
          
          // Anthropic API hosts the model traffic legitimately reaches.
          export const ANTHROPIC_HOSTS = ['api.anthropic.com', 'anthropic.com'];
          
          function _host(u) {
            try { return new URL(u).hostname.toLowerCase(); } catch { return ''; }
          }
          
          // Build the allowlist of hostnames from the ops API url plus Anthropic.
          export function egressAllowlist({ opsUrl = process.env.BEANS_OPS_URL, extra = [] } = {}) {
            const hosts = new Set(ANTHROPIC_HOSTS.map((h) => h.toLowerCase()));
            const opsHost = _host(opsUrl);
            if (opsHost) hosts.add(opsHost);
            for (const e of extra) { const h = (e || '').toLowerCase(); if (h) hosts.add(h); }
            return hosts;
          }
          
          // True iff `url`'s host is on the allowlist (exact host or a subdomain of an allowed host).
          export function isEgressAllowed(url, allowlist) {
            const host = _host(url);
            if (!host) return false;
            for (const a of allowlist) {
              if (host === a || host.endsWith('.' + a)) return true;
            }
            return false;
          }
          
          // Throw on a disallowed host (the fetch-guard). Fail closed.
          export function assertEgressAllowed(url, allowlist) {
            if (!isEgressAllowed(url, allowlist)) {
              throw new Error('EGRESS-BLOCKED ' + (_host(url) || url));
            }
          }
          
          // Wrap a fetch so every outbound call is checked against the allowlist first.
          export function guardedFetch(allowlist, fetchImpl = fetch) {
            return async function (url, opts) {
              assertEgressAllowed(url, allowlist); // throws -> rejected promise (fail closed)
              return fetchImpl(url, opts);
            };
          }
          
          // Boot check: the allowlist must contain the ops host AND Anthropic, or we refuse to serve
          // (a box that cannot name where it may talk is misconfigured). Returns {ok, allowlist, reason}.
          export function verifyEgressConfig({ opsUrl = process.env.BEANS_OPS_URL } = {}) {
            const allowlist = egressAllowlist({ opsUrl });
            const opsHost = _host(opsUrl);
            if (!opsHost) return { ok: false, allowlist: [...allowlist], reason: 'ops-url-missing-or-invalid' };
            const hasAnthropic = ANTHROPIC_HOSTS.some((h) => allowlist.has(h));
            if (!hasAnthropic) return { ok: false, allowlist: [...allowlist], reason: 'anthropic-host-absent' };
            return { ok: true, allowlist: [...allowlist], reason: null };
          }
          
          // CLI: node egress-guard.mjs. Exit 0 if the egress config is sane, 1 otherwise (fail closed).
          function main() {
            const r = verifyEgressConfig();
            if (r.ok) {
              console.log('EGRESS-OK allow=' + JSON.stringify(r.allowlist));
              process.exit(0);
            }
            console.error('EGRESS-FAIL reason=' + r.reason + ' allow=' + JSON.stringify(r.allowlist));
            process.exit(1);
          }
          
          import { fileURLToPath } from 'node:url';
          if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
            main();
          }
        EOJS
      }

      # The beans MCP tool server the agent child loads. Holds no DB credentials; calls the internal
      # operation API with the internal token and the pinned tenant from env. Embedded by build-hcl.mjs.
      template {
        destination = "local/beans-mcp.mjs"
        perms       = "0644"
        data        = <<-EOJS
          // Beans MCP server (spec 007, the tool layer). Line-delimited JSON-RPC 2.0 over stdio.
          //
          // These tools hold NO database credentials (D-036). Each calls the Next.js internal
          // operation API (spec 010: BEANS_OPS_URL repointed from the dead FastAPI to the Next app,
          // e.g. https://<app>/api, so a tool path like /internal/ops/read_stock resolves to
          // https://<app>/api/internal/ops/read_stock) with the internal service token and the tenant
          // pinned OUT OF BAND: the gateway injects BEANS_TENANT_PHONE per request, the tool sends it as
          // the x-beans-tenant header, and the model never sees or sets it (D-037). There is no commit
          // tool and never will be; writes are two-phase previews that land in M3+ (D-038).
          //
          // M1 shipped one read tool (read_stock). M2 adds the rest of the read surface (s-04):
          // revenue, profit, sales summary, the eight command-center module snapshots, and a
          // business_status tool that reads the one existing attention aggregation (AC6). Every
          // tool argument here is a non-tenant parameter (a limit, a module id); the tenant is
          // never a tool argument. The HTTP call and the message dispatch are exported so they
          // unit-test with an injected fetch, no network and no spawned child.
          import process from 'node:process';
          import { egressAllowlist, isEgressAllowed } from './egress-guard.mjs';
          
          // The eight command-center modules, by their registry ids. read_module takes one of
          // these so the owner can ask about a single domain ("¿cómo van los costos?"); the set
          // is fixed and model-closed (additionalProperties:false) so a hallucinated module id is
          // a tool error, never a silent wrong read.
          export const MODULE_IDS = [
            'caja', 'productos', 'stock', 'ventas', 'costos', 'produccion', 'logistica', 'proveedores',
          ];
          
          export const TOOLS = [
            {
              name: 'read_stock',
              description:
                'Read the current stock (units on hand per product) for the business. Takes no arguments; ' +
                'the business is fixed for this session. Use it when the owner asks how much of something is left.',
              inputSchema: { type: 'object', properties: {}, additionalProperties: false },
            },
            {
              name: 'read_revenue',
              description:
                'Read the business total revenue (ingresos). Takes no arguments. Use it when the owner asks ' +
                'how much the business has sold or billed in total.',
              inputSchema: { type: 'object', properties: {}, additionalProperties: false },
            },
            {
              name: 'read_profit',
              description:
                'Read the business profit (ganancia). Takes no arguments. Use it when the owner asks how much ' +
                'the business is earning or netting.',
              inputSchema: { type: 'object', properties: {}, additionalProperties: false },
            },
            {
              name: 'read_sales_summary',
              description:
                'Read a day-by-day summary of recent paid sales (count and revenue per day). Optional "limit" ' +
                'is how many recent days to include (1 to 50, default 10). Use it when the owner asks how sales ' +
                'have been going lately.',
              inputSchema: {
                type: 'object',
                properties: { limit: { type: 'integer', minimum: 1, maximum: 50 } },
                additionalProperties: false,
              },
            },
            {
              name: 'read_module',
              description:
                'Read one command-center module\'s current headline and anything in it that needs attention. ' +
                '"module" is one of: caja (Resultado/net), productos, stock, ventas, costos, produccion, ' +
                'logistica, proveedores. Use it when the owner asks about one specific area of the business.',
              inputSchema: {
                type: 'object',
                properties: { module: { type: 'string', enum: MODULE_IDS } },
                required: ['module'],
                additionalProperties: false,
              },
            },
            {
              name: 'business_status',
              description:
                'Read the one prioritized "what needs attention today" list across the whole business (overdue ' +
                'arrivals, overdue supplier check-ins, pending customs). Takes no arguments. Use it when the owner asks how the business is doing ' +
                'or what needs them today. This is the same list the command-center home shows; never invent items.',
              inputSchema: { type: 'object', properties: {}, additionalProperties: false },
            },
            // ── Write-PREVIEW tools (spec 007 M3). These PREPARE a write; they never record it. ──
            // There is still no commit tool: the owner confirms in the command center (or an obvious,
            // reversible, owner-grounded write is auto-confirmed by the client). After calling one,
            // tell the owner what you prepared — do NOT say it is already saved.
            {
              name: 'register_sale',
              description:
                'Prepare recording a sale. Does NOT record it by itself: it stages a proposal the owner confirms ' +
                '(or that is auto-confirmed when it is obvious and reversible). "product" is what was sold; ' +
                '"quantity" defaults to 1; "unit_amount" is the price per unit the owner stated, in whole currency ' +
                'units (e.g. 400), when they stated one. After calling, tell the owner what you prepared; never claim ' +
                'it is already saved.',
              inputSchema: {
                type: 'object',
                properties: {
                  product: { type: 'string' },
                  quantity: { type: 'integer', minimum: 1 },
                  unit_amount: { type: 'number' },
                },
                required: ['product'],
                additionalProperties: false,
              },
            },
            {
              name: 'register_expense',
              description:
                'Prepare recording a business expense. Does NOT record it by itself. "amount" is the amount in whole ' +
                'currency units the owner stated; "description" is what it was for; "category" is optional. After ' +
                'calling, tell the owner what you prepared; never claim it is already saved.',
              inputSchema: {
                type: 'object',
                properties: {
                  amount: { type: 'number' },
                  description: { type: 'string' },
                  category: { type: 'string' },
                },
                required: ['amount', 'description'],
                additionalProperties: false,
              },
            },
            {
              name: 'add_stock',
              description:
                'Prepare adding stock (units on hand) to a product. Does NOT record it by itself. "product" is the ' +
                'product; "quantity" is how many units to add. After calling, tell the owner what you prepared; never ' +
                'claim it is already saved.',
              inputSchema: {
                type: 'object',
                properties: {
                  product: { type: 'string' },
                  quantity: { type: 'integer', minimum: 1 },
                },
                required: ['product', 'quantity'],
                additionalProperties: false,
              },
            },
            // ── Confirm-only write previews (spec 007 M4, D-044): irreversible / bulk / destructive. ──
            // These ALWAYS wait for the owner to confirm (they never auto-complete). Prepare them, then
            // tell the owner what will change and that it needs their confirmation; never claim it is done.
            {
              name: 'update_product_price',
              description:
                'Prepare CHANGING a product\'s sale price. Irreversible (the old price is not kept), so it always ' +
                'needs the owner\'s confirmation. "product" is the product; "new_amount" is the new price in whole ' +
                'currency units. After calling, tell the owner the old and new price and that they must confirm.',
              inputSchema: {
                type: 'object',
                properties: { product: { type: 'string' }, new_amount: { type: 'number' } },
                required: ['product', 'new_amount'],
                additionalProperties: false,
              },
            },
            {
              name: 'register_product',
              description:
                'Prepare CREATING a new product in the catalog. Always needs the owner\'s confirmation. "name" is the ' +
                'product name; "price_amount" is its sale price in whole currency units; "cost_amount" is optional.',
              inputSchema: {
                type: 'object',
                properties: {
                  name: { type: 'string' },
                  price_amount: { type: 'number' },
                  cost_amount: { type: 'number' },
                },
                required: ['name', 'price_amount'],
                additionalProperties: false,
              },
            },
            {
              name: 'register_products_batch',
              description:
                'Prepare CREATING several products at once. Each product is prepared as its OWN confirm card, so ' +
                'the owner confirms each one (nothing is created until they do). After calling, tell the owner how ' +
                'many products you prepared and that each needs their confirmation. "products" is a list, each with ' +
                '"name" and "price_amount" (and optional "cost_amount").',
              inputSchema: {
                type: 'object',
                properties: {
                  products: {
                    type: 'array',
                    items: {
                      type: 'object',
                      properties: {
                        name: { type: 'string' },
                        price_amount: { type: 'number' },
                        cost_amount: { type: 'number' },
                      },
                      required: ['name', 'price_amount'],
                      additionalProperties: false,
                    },
                  },
                },
                required: ['products'],
                additionalProperties: false,
              },
            },
            {
              name: 'deactivate_product',
              description:
                'Prepare DEACTIVATING (hiding) a product so it is no longer sold. Always needs the owner\'s ' +
                'confirmation. "product" is the product to deactivate.',
              inputSchema: {
                type: 'object',
                properties: { product: { type: 'string' } },
                required: ['product'],
                additionalProperties: false,
              },
            },
            {
              name: 'cancel_last_operation',
              description:
                'Prepare CANCELLING the most recent operation (the last sale, expense, or stock entry). Takes no ' +
                'arguments. Always needs the owner\'s confirmation and shows exactly which operation would be cancelled.',
              inputSchema: { type: 'object', properties: {}, additionalProperties: false },
            },
          ];
          
          // Generic call to an internal read endpoint. Returns an MCP tool-result content object.
          // Never throws for an operational failure: it returns an is_error content so the model
          // can tell the owner something went wrong instead of the loop crashing. `label` names the
          // tool in any error message; `resultKey` is the field lifted from the {ok:true,...} body.
          export async function callRead(
            { opsUrl, token, phone, path, body = '{}', fetchImpl = fetch } = {},
            { label, resultKey } = {},
          ) {
            if (!opsUrl || !token || !phone) {
              return { content: [{ type: 'text', text: `$${label} not configured (missing ops url, token, or tenant).` }], isError: true };
            }
            const url = opsUrl.replace(/\/$/, '') + path;
            // Egress allowlist (AC12): a tool may only ever reach the ops API (+ Anthropic). Fail closed.
            if (!isEgressAllowed(url, egressAllowlist({ opsUrl }))) {
              return { content: [{ type: 'text', text: `$${label} blocked: egress not allowed to $${url}` }], isError: true };
            }
            let res;
            try {
              res = await fetchImpl(url, {
                method: 'POST',
                headers: {
                  'content-type': 'application/json',
                  'x-internal-token': token,
                  'x-beans-tenant': phone,
                },
                body,
              });
            } catch (e) {
              return { content: [{ type: 'text', text: `$${label} could not reach the operation API: ` + e.message }], isError: true };
            }
            let payload;
            try { payload = await res.json(); } catch { payload = null; }
            if (!res.ok || !payload || payload.ok !== true) {
              const msg = (payload && payload.error && payload.error.message) || (`$${label} failed (HTTP ` + res.status + ')');
              return { content: [{ type: 'text', text: msg }], isError: true };
            }
            // Return only the named result field, under a stable top-level key, so the model gets a
            // tight JSON blob rather than the transport envelope.
            const out = resultKey ? { [resultKey]: payload[resultKey] } : payload;
            return { content: [{ type: 'text', text: JSON.stringify(out) }] };
          }
          
          export async function readStock(cfg = {}) {
            return callRead({ ...cfg, path: '/internal/ops/read_stock' }, { label: 'read_stock', resultKey: 'stock' });
          }
          
          export async function readRevenue(cfg = {}) {
            return callRead({ ...cfg, path: '/internal/ops/read_revenue' }, { label: 'read_revenue', resultKey: 'revenue' });
          }
          
          export async function readProfit(cfg = {}) {
            return callRead({ ...cfg, path: '/internal/ops/read_profit' }, { label: 'read_profit', resultKey: 'profit' });
          }
          
          export async function readSalesSummary(cfg = {}, { limit } = {}) {
            const body = JSON.stringify(Number.isInteger(limit) ? { limit } : {});
            return callRead({ ...cfg, path: '/internal/ops/read_sales_summary', body }, { label: 'read_sales_summary', resultKey: 'sales_summary' });
          }
          
          export async function readModule(cfg = {}, { module } = {}) {
            const body = JSON.stringify({ module });
            return callRead({ ...cfg, path: '/internal/ops/read_module', body }, { label: 'read_module', resultKey: 'module' });
          }
          
          export async function businessStatus(cfg = {}) {
            return callRead({ ...cfg, path: '/internal/ops/business_status' }, { label: 'business_status', resultKey: 'attention' });
          }
          
          // Call an internal write-PREVIEW endpoint. Returns the staged preview (or a clarify) to the
          // model, but NEVER the op_token: the commit handle travels only to the owner's browser via the
          // chat envelope metadata, so even a hijacked model holds nothing that could commit (D-040).
          export async function callPreview({ opsUrl, token, phone, path, body = '{}', turnNonce, flowNonce, owner, fetchImpl = fetch } = {}, { label } = {}) {
            if (!opsUrl || !token || !phone) {
              return { content: [{ type: 'text', text: `$${label} not configured (missing ops url, token, or tenant).` }], isError: true };
            }
            const url = opsUrl.replace(/\/$/, '') + path;
            if (!isEgressAllowed(url, egressAllowlist({ opsUrl }))) {
              return { content: [{ type: 'text', text: `$${label} blocked: egress not allowed to $${url}` }], isError: true };
            }
            const headers = { 'content-type': 'application/json', 'x-internal-token': token, 'x-beans-tenant': phone };
            // Pin the per-turn nonce out of band so the server stamps the staged op with this turn's id,
            // and the flow nonce + owner so the internal endpoint grounds the verdict against the
            // server-authenticated operator_turns record keyed by (owner, flowNonce), NEVER these tool
            // args (spec 010 M3, T-015/T-014, D-061). All three come from the gateway-injected child env,
            // never from the model: the model cannot read or set a header.
            if (turnNonce) headers['x-beans-turn'] = turnNonce;
            if (flowNonce) headers['x-beans-flow'] = flowNonce;
            if (owner) headers['x-beans-owner'] = owner;
            let res;
            try {
              res = await fetchImpl(url, { method: 'POST', headers, body });
            } catch (e) {
              return { content: [{ type: 'text', text: `$${label} could not reach the operation API: ` + e.message }], isError: true };
            }
            let payload;
            try { payload = await res.json(); } catch { payload = null; }
            if (!res.ok || !payload || payload.ok !== true) {
              const msg = (payload && payload.error && payload.error.message) || (`$${label} failed (HTTP ` + res.status + ')');
              return { content: [{ type: 'text', text: msg }], isError: true };
            }
            // Strip the transport ok flag and the commit handle before handing anything to the model.
            const { ok, op_token, ...visible } = payload; // eslint-disable-line no-unused-vars
            return { content: [{ type: 'text', text: JSON.stringify(visible) }] };
          }
          
          export async function registerSale(cfg = {}, { product, quantity, unit_amount } = {}) {
            const body = JSON.stringify({ product, quantity, unit_amount });
            return callPreview({ ...cfg, path: '/internal/ops/preview/register_sale', body }, { label: 'register_sale' });
          }
          
          export async function registerExpense(cfg = {}, { amount, description, category } = {}) {
            const body = JSON.stringify({ amount, description, category });
            return callPreview({ ...cfg, path: '/internal/ops/preview/register_expense', body }, { label: 'register_expense' });
          }
          
          export async function addStock(cfg = {}, { product, quantity } = {}) {
            const body = JSON.stringify({ product, quantity });
            return callPreview({ ...cfg, path: '/internal/ops/preview/add_stock', body }, { label: 'add_stock' });
          }
          
          export async function updateProductPrice(cfg = {}, { product, new_amount } = {}) {
            const body = JSON.stringify({ product, new_amount });
            return callPreview({ ...cfg, path: '/internal/ops/preview/update_product_price', body }, { label: 'update_product_price' });
          }
          
          export async function registerProduct(cfg = {}, { name, price_amount, cost_amount } = {}) {
            const body = JSON.stringify({ name, price_amount, cost_amount });
            return callPreview({ ...cfg, path: '/internal/ops/preview/register_product', body }, { label: 'register_product' });
          }
          
          export async function registerProductsBatch(cfg = {}, { products } = {}) {
            const body = JSON.stringify({ products });
            return callPreview({ ...cfg, path: '/internal/ops/preview/register_products_batch', body }, { label: 'register_products_batch' });
          }
          
          export async function deactivateProduct(cfg = {}, { product } = {}) {
            const body = JSON.stringify({ product });
            return callPreview({ ...cfg, path: '/internal/ops/preview/deactivate_product', body }, { label: 'deactivate_product' });
          }
          
          export async function cancelLastOperation(cfg = {}) {
            return callPreview({ ...cfg, path: '/internal/ops/preview/cancel_last_operation', body: '{}' }, { label: 'cancel_last_operation' });
          }
          
          // Build a JSON-RPC dispatcher. Each `*Impl` is injectable for tests.
          export function makeDispatcher({
            readStockImpl = readStock,
            readRevenueImpl = readRevenue,
            readProfitImpl = readProfit,
            readSalesSummaryImpl = readSalesSummary,
            readModuleImpl = readModule,
            businessStatusImpl = businessStatus,
            registerSaleImpl = registerSale,
            registerExpenseImpl = registerExpense,
            addStockImpl = addStock,
            updateProductPriceImpl = updateProductPrice,
            registerProductImpl = registerProduct,
            registerProductsBatchImpl = registerProductsBatch,
            deactivateProductImpl = deactivateProduct,
            cancelLastOperationImpl = cancelLastOperation,
            config = {},
          } = {}) {
            return async function dispatch(msg) {
              const { id, method, params } = msg || {};
              if (method === 'initialize') {
                const pv = (params && params.protocolVersion) || '2024-11-05';
                return { jsonrpc: '2.0', id, result: { protocolVersion: pv, capabilities: { tools: {} }, serverInfo: { name: 'beans', version: '0.2.0' } } };
              }
              if (method && method.startsWith('notifications/')) return null; // notifications get no response
              if (method === 'tools/list') {
                return { jsonrpc: '2.0', id, result: { tools: TOOLS } };
              }
              if (method === 'tools/call') {
                const name = params && params.name;
                const args = (params && params.arguments) || {};
                let r;
                if (name === 'read_stock') r = await readStockImpl(config);
                else if (name === 'read_revenue') r = await readRevenueImpl(config);
                else if (name === 'read_profit') r = await readProfitImpl(config);
                else if (name === 'read_sales_summary') r = await readSalesSummaryImpl(config, { limit: args.limit });
                else if (name === 'read_module') r = await readModuleImpl(config, { module: args.module });
                else if (name === 'business_status') r = await businessStatusImpl(config);
                else if (name === 'register_sale') r = await registerSaleImpl(config, { product: args.product, quantity: args.quantity, unit_amount: args.unit_amount });
                else if (name === 'register_expense') r = await registerExpenseImpl(config, { amount: args.amount, description: args.description, category: args.category });
                else if (name === 'add_stock') r = await addStockImpl(config, { product: args.product, quantity: args.quantity });
                else if (name === 'update_product_price') r = await updateProductPriceImpl(config, { product: args.product, new_amount: args.new_amount });
                else if (name === 'register_product') r = await registerProductImpl(config, { name: args.name, price_amount: args.price_amount, cost_amount: args.cost_amount });
                else if (name === 'register_products_batch') r = await registerProductsBatchImpl(config, { products: args.products });
                else if (name === 'deactivate_product') r = await deactivateProductImpl(config, { product: args.product });
                else if (name === 'cancel_last_operation') r = await cancelLastOperationImpl(config);
                else return { jsonrpc: '2.0', id, error: { code: -32601, message: 'unknown tool ' + name } };
                return { jsonrpc: '2.0', id, result: r };
              }
              if (id !== undefined && id !== null) return { jsonrpc: '2.0', id, result: {} };
              return null;
            };
          }
          
          // stdio main loop: read line-delimited JSON-RPC, dispatch, write responses.
          function main() {
            const config = {
              opsUrl: process.env.BEANS_OPS_URL,
              token: process.env.INTERNAL_SERVICE_TOKEN,
              phone: process.env.BEANS_TENANT_PHONE,
              // The gateway injects these per request (out of band, never a model input): the turn nonce
              // stamps a staged write; the flow nonce + owner let the internal endpoint ground the verdict
              // against operator_turns keyed by (owner, flowNonce) (spec 010 M3, T-015, D-061).
              turnNonce: process.env.BEANS_TURN_NONCE,
              flowNonce: process.env.BEANS_FLOW_NONCE,
              owner: process.env.BEANS_OWNER,
            };
            const dispatch = makeDispatcher({ config });
            const send = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');
            let buf = '';
            process.stdin.setEncoding('utf8');
            process.stdin.on('data', (chunk) => {
              buf += chunk;
              let idx;
              while ((idx = buf.indexOf('\n')) >= 0) {
                const line = buf.slice(0, idx).trim();
                buf = buf.slice(idx + 1);
                if (!line) continue;
                let msg;
                try { msg = JSON.parse(line); } catch { continue; }
                Promise.resolve(dispatch(msg)).then((resp) => { if (resp) send(resp); });
              }
            });
          }
          
          import { fileURLToPath } from 'node:url';
          if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
            main();
          }
        EOJS
      }

      # Static MCP config the agent child runs with: launches /local/beans-mcp.mjs as server "beans".
      # The MCP server inherits BEANS_OPS_URL / INTERNAL_SERVICE_TOKEN / BEANS_TENANT_PHONE from the
      # gateway env (single business: the tenant is a fixed, out-of-band value, never a model param).
      template {
        destination = "local/mcp-beans.json"
        perms       = "0644"
        data        = <<-EOJSON
          {"mcpServers":{"beans":{"command":"node","args":["/local/beans-mcp.mjs"]}}}
        EOJSON
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
