// deploy/gateway.test.mjs — offline tests for the beans-ai warm gateway.
//
// No real `claude` binary and no subscription token: a fake child speaks the stream-json
// protocol, so the full lease -> turn -> parse -> HTTP path is exercised deterministically.
//
// Run: node deploy/gateway.test.mjs   (uses node:test; exits non-zero on any failure)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import {
  createGateway,
  ChildPool,
  runWarmTurn,
  extractResult,
  carveJson,
  userTurnLine,
} from './gateway.mjs';
import { render } from './build-hcl.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));

// A fake `claude -p --input-format stream-json` child. On stdin.end() it emits the canned
// stream-json events on stdout then ends — the shape the real CLI produces.
function fakeChildFactory(reply, { delayMs = 1 } = {}) {
  return function spawnFake() {
    const child = new EventEmitter();
    let written = '';
    child.stdout = new EventEmitter();
    child.stdin = {
      destroyed: false,
      write(chunk) {
        written += chunk;
        return true;
      },
      end() {
        // Respond asynchronously, like a real child.
        setTimeout(() => {
          const events = [
            { type: 'assistant', message: { role: 'assistant', content: [{ type: 'text', text: reply }] } },
            { type: 'result', subtype: 'success', result: reply, is_error: false },
          ];
          for (const e of events) child.stdout.emit('data', Buffer.from(JSON.stringify(e) + '\n'));
          child.stdout.emit('end');
          child.emit('exit', 0);
        }, delayMs);
      },
    };
    child.kill = () => {};
    child._written = () => written;
    return child;
  };
}

// A child that never answers (for the warm-timeout -> one-shot fallback test).
function hangingChildFactory() {
  return function spawnHang() {
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stdin = { destroyed: false, write() {}, end() {} };
    child.kill = () => {};
    return child;
  };
}

async function listen(server) {
  await new Promise((r) => server.listen(0, r));
  const { port } = server.address();
  return `http://127.0.0.1:${port}`;
}

const SECRET = 'test-secret-xyz';

test('userTurnLine produces one JSONL user message', () => {
  const line = userTurnLine('hola');
  assert.ok(line.endsWith('\n'));
  const j = JSON.parse(line);
  assert.equal(j.type, 'user');
  assert.equal(j.message.content[0].text, 'hola');
});

test('extractResult prefers the result event, falls back to assistant text', () => {
  assert.equal(extractResult([{ type: 'result', result: 'R' }]), 'R');
  assert.equal(
    extractResult([{ type: 'assistant', message: { content: [{ type: 'text', text: 'A' }] } }]),
    'A'
  );
});

test('carveJson extracts the first balanced object and rejects non-json', () => {
  assert.deepEqual(carveJson('noise {"intent":"READ"} tail'), { intent: 'READ' });
  assert.throws(() => carveJson('no object here'));
});

test('ChildPool refills to target and replaces a leased child', () => {
  const pool = new ChildPool({ poolTarget: 2, spawnChild: fakeChildFactory('x') });
  pool.refill();
  assert.equal(pool.ready, 2);
  const c = pool.lease();
  assert.ok(c);
  // lease schedules an async refill; drain the microtask/timer queue
  return new Promise((r) => setImmediate(() => { pool.refill(); assert.equal(pool.ready, 2); pool.close(); r(); }));
});

test('runWarmTurn writes one turn and returns the assistant text', async () => {
  const child = fakeChildFactory('{"intent":"REGISTER_SALE"}')();
  const text = await runWarmTurn(child, 'vendí una tabla', { timeoutMs: 2000 });
  assert.equal(text, '{"intent":"REGISTER_SALE"}');
});

test('GET /health reports pool readiness', async () => {
  const server = createGateway({ secret: SECRET, poolTarget: 2, spawnChild: fakeChildFactory('x') });
  const base = await listen(server);
  const r = await fetch(base + '/health');
  const j = await r.json();
  assert.equal(r.status, 200);
  assert.equal(j.ok, true);
  assert.equal(j.svc, 'beans-ai');
  assert.equal(j.pool.target, 2);
  server.close();
});

test('POST /run without bearer is 401 with a named-error envelope', async () => {
  const server = createGateway({ secret: SECRET, spawnChild: fakeChildFactory('x') });
  const base = await listen(server);
  const r = await fetch(base + '/run', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ prompt: 'hi' }),
  });
  const j = await r.json();
  assert.equal(r.status, 401);
  assert.equal(j.ok, false);
  assert.equal(j.error.code, 'unauthorized');
  assert.ok(typeof j.error.message === 'string');
  server.close();
});

test('POST /run (warm) returns text for a classification prompt', async () => {
  const server = createGateway({
    secret: SECRET,
    poolTarget: 2,
    spawnChild: fakeChildFactory('{"intent":"READ_ANALYTICS","confidence":0.9}'),
  });
  const base = await listen(server);
  const r = await fetch(base + '/run', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + SECRET },
    body: JSON.stringify({ system: 'Sos el router de Timonel.', prompt: 'cuánto vendí hoy' }),
  });
  const j = await r.json();
  assert.equal(r.status, 200);
  assert.equal(j.ok, true);
  assert.equal(j.path, 'warm');
  assert.ok(j.text.includes('READ_ANALYTICS'));
  server.close();
});

test('POST /run with json_schema returns parsed json', async () => {
  const server = createGateway({
    secret: SECRET,
    poolTarget: 1,
    spawnChild: fakeChildFactory('aquí: {"intent":"REGISTER_EXPENSE","confidence":0.8}'),
  });
  const base = await listen(server);
  const r = await fetch(base + '/run', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + SECRET },
    body: JSON.stringify({ prompt: 'pagué 5000 de nafta', json_schema: { intent: 'string' } }),
  });
  const j = await r.json();
  assert.equal(r.status, 200);
  assert.equal(j.ok, true);
  assert.deepEqual(j.json, { intent: 'REGISTER_EXPENSE', confidence: 0.8 });
  server.close();
});

test('POST /run bad json body is 400', async () => {
  const server = createGateway({ secret: SECRET, spawnChild: fakeChildFactory('x') });
  const base = await listen(server);
  const r = await fetch(base + '/run', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + SECRET },
    body: '{not json',
  });
  const j = await r.json();
  assert.equal(r.status, 400);
  assert.equal(j.error.code, 'bad-json');
  server.close();
});

test('POST /run empty prompt is 400', async () => {
  const server = createGateway({ secret: SECRET, spawnChild: fakeChildFactory('x') });
  const base = await listen(server);
  const r = await fetch(base + '/run', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + SECRET },
    body: JSON.stringify({ prompt: '   ' }),
  });
  const j = await r.json();
  assert.equal(r.status, 400);
  assert.equal(j.error.code, 'empty-prompt');
  server.close();
});

test('warm failure falls back to one-shot (injected)', async () => {
  let oneShotCalled = false;
  const server = createGateway({
    secret: SECRET,
    poolTarget: 1,
    spawnChild: hangingChildFactory(),
    warm: { timeoutMs: 80 }, // force the warm turn to time out fast
    oneShotFn: async (text) => {
      oneShotCalled = true;
      return '{"intent":"GREETING"}';
    },
  });
  const base = await listen(server);
  const r = await fetch(base + '/run', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + SECRET },
    body: JSON.stringify({ prompt: 'hola' }),
  });
  const j = await r.json();
  assert.equal(r.status, 200);
  assert.equal(j.ok, true);
  assert.equal(j.path, 'one-shot');
  assert.ok(oneShotCalled);
  assert.ok(j.text.includes('GREETING'));
  server.close();
});

test('empty pool goes straight to one-shot (injected)', async () => {
  const server = createGateway({
    secret: SECRET,
    poolTarget: 0, // no warm children
    spawnChild: fakeChildFactory('x'),
    oneShotFn: async () => '{"intent":"PRODUCT_INFO"}',
  });
  const base = await listen(server);
  const r = await fetch(base + '/run', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + SECRET },
    body: JSON.stringify({ prompt: 'qué tabla tengo' }),
  });
  const j = await r.json();
  assert.equal(j.ok, true);
  assert.equal(j.path, 'one-shot');
  server.close();
});

test('createGateway requires a secret', () => {
  assert.throws(() => createGateway({ secret: '' }));
});

test('committed beans-ai.nomad.hcl is in sync with gateway.mjs (run node deploy/build-hcl.mjs)', () => {
  const committed = readFileSync(join(HERE, 'beans-ai.nomad.hcl'), 'utf8');
  assert.equal(committed, render(), 'HCL drifted from gateway.mjs — regenerate with build-hcl.mjs');
});

test('beans-ai.nomad.hcl is structurally sound', () => {
  const hcl = readFileSync(join(HERE, 'beans-ai.nomad.hcl'), 'utf8');
  assert.ok(!hcl.includes('@@GATEWAY_MJS@@'), 'marker not replaced');
  assert.ok(hcl.includes('job "beans-ai"'));
  assert.ok(hcl.includes('CLAUDE_CODE_OAUTH_TOKEN={{ .CLAUDE_CODE_OAUTH_TOKEN }}'));
  assert.ok(hcl.includes('BEANS_AI_SHARED_SECRET={{ .BEANS_AI_SHARED_SECRET }}'));
  assert.ok(hcl.includes('Host(`beans-ai.mdlautomations.duckdns.org`)'));
  assert.ok(hcl.includes('path     = "/health"'));
  assert.ok(hcl.includes('export function createGateway'), 'gateway not embedded');
  // isolation self-check must fail closed on GOOGLE/GEMINI (the Gemini key we are replacing)
  assert.ok(/grep -iE '[^']*GOOGLE[^']*GEMINI/.test(hcl), 'isolation grep must block GOOGLE and GEMINI');
  // balanced top-level braces
  const opens = (hcl.match(/\{/g) || []).length;
  const closes = (hcl.match(/\}/g) || []).length;
  assert.equal(opens, closes, 'unbalanced braces in HCL');
});
