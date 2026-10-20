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

// The tool-mode flags, shared by the real turn and the boot self-check so they probe what runs.
function agentFlags(mcpConfig = BEANS_MCP_CONFIG) {
  return [
    '--allowedTools', 'mcp__beans__*',
    '--disallowedTools', ...TOOL_MODE_DISALLOWED,
    '--mcp-config', mcpConfig,
    '--strict-mcp-config',
  ];
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
function runAgentTurn(userText, { claudeBin, cwd, token, system, mcpConfig = BEANS_MCP_CONFIG, maxTurns = AGENT_MAX_TURNS, timeoutMs = DEFAULTS.runTimeoutMs, spawnChild } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let out = '';
    const args = [
      '-p',
      '--input-format', 'stream-json',
      '--output-format', 'stream-json',
      '--verbose',
      '--max-turns', String(maxTurns),
      ...(system ? ['--append-system-prompt', system] : []),
      ...agentFlags(mcpConfig),
    ];
    let child;
    try {
      child = spawnChild
        ? spawnChild(args, token)
        : spawn(claudeBin || process.env.CLAUDE_BIN || 'claude', args, {
            cwd: cwd || '/alloc/data',
            stdio: ['pipe', 'pipe', 'ignore'],
            env: childSpawnEnv(process.env, token || null),
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
    }
    const server = createGateway({ cwd });
    server.listen(port, () => console.log('[beans-ai] warm gateway http on ' + port));
  })();
}
