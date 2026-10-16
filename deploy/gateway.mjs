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
      { cwd: this.cwd, stdio: ['pipe', 'pipe', 'ignore'] }
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
function runOneShot(text, { claudeBin, cwd, timeoutMs = DEFAULTS.oneShotTimeoutMs } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let out = '';
    const child = spawn(
      claudeBin || process.env.CLAUDE_BIN || 'claude',
      ['-p', text, '--output-format', 'json', '--max-turns', '1', ...SAFE_ARGS],
      { cwd: cwd || '/alloc/data', stdio: ['ignore', 'pipe', 'ignore'] }
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

// Resolve one /run: lease a warm child, fall back to one-shot. `combine` makes the single user
// turn text. Returns the assistant text; the HTTP layer shapes {ok, text|json}.
async function resolveRun(pool, { system, prompt }, opts = {}) {
  const combined = (system ? system + '\n\n' : '') + prompt;
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
  const text = await oneShotFn(combined, {
    claudeBin: pool.claudeBin,
    cwd: pool.cwd,
    ...(opts.oneShot || {}),
  });
  return { text, path: 'one-shot' };
}

function makeHandler(pool, secret, runOpts = {}) {
  return function handler(req, res) {
    if (req.method === 'GET' && req.url === '/health') {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(
        JSON.stringify({
          ok: true,
          svc: 'beans-ai',
          pool: { ready: pool.ready, target: pool.target },
          backend: 'claude-subscription',
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
  const pool = new ChildPool(opts);
  pool.refill();
  const server = http.createServer(
    makeHandler(pool, secret, { oneShotFn: opts.oneShotFn, warm: opts.warm, oneShot: opts.oneShot })
  );
  const origClose = server.close.bind(server);
  server.close = (cb) => {
    pool.close();
    return origClose(cb);
  };
  server._pool = pool; // test hook
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
