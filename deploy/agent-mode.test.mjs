// deploy/agent-mode.test.mjs — offline tests for the native tool-use path (spec 007 /run-agent).
// The live end-to-end loop (real claude + beans MCP + internal endpoint) is proven separately; these
// pin the orchestration deterministically with an injected agentFn: bearer gate, rotation on a
// usage-limit turn, and the {ok,text} envelope.
//
// Run: node deploy/agent-mode.test.mjs   (node:test; exits non-zero on any failure)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createGateway, resolveAgent } from './gateway.mjs';
import { TokenPool } from './token-pool.mjs';

const SECRET = 'agent-secret';
const LIMIT = 'Claude AI usage limit reached|1799999999';

async function listen(server) {
  await new Promise((r) => server.listen(0, r));
  return `http://127.0.0.1:${server.address().port}`;
}

test('resolveAgent rotates past an exhausted account to a healthy one', async () => {
  const tokenPool = new TokenPool(['A', 'B']);
  const agentFn = async (_combined, { token }) => (token === 'A' ? LIMIT : 'answer-from-B');
  const { text, path } = await resolveAgent('cuanto stock', { tokenPool, agentFn });
  assert.equal(text, 'answer-from-B');
  assert.equal(path, 'agent');
  assert.equal(tokenPool.active(), 'B');
});

test('resolveAgent throws the honest message when every account is exhausted', async () => {
  const tokenPool = new TokenPool(['A', 'B']);
  const agentFn = async () => LIMIT;
  await assert.rejects(resolveAgent('x', { tokenPool, agentFn }), /limite de uso/);
});

test('POST /run-agent returns {ok,text} with the agent path', async () => {
  const server = createGateway({
    secret: SECRET,
    spawnChild: () => null, // no warm pool needed for the agent path
    tokens: ['A'],
    agentFn: async () => 'Te quedan 48 unidades.',
  });
  const base = await listen(server);
  const r = await fetch(base + '/run-agent', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + SECRET },
    body: JSON.stringify({ system: 'sos el asistente', prompt: 'cuanto stock' }),
  });
  const j = await r.json();
  assert.equal(r.status, 200);
  assert.equal(j.ok, true);
  assert.equal(j.path, 'agent');
  assert.match(j.text, /48/);
  server.close();
});

test('POST /run-agent without bearer is 401 with the named envelope', async () => {
  const server = createGateway({ secret: SECRET, spawnChild: () => null, tokens: ['A'], agentFn: async () => 'x' });
  const base = await listen(server);
  const r = await fetch(base + '/run-agent', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ prompt: 'hola' }),
  });
  const j = await r.json();
  assert.equal(r.status, 401);
  assert.equal(j.ok, false);
  assert.equal(j.error.code, 'unauthorized');
  server.close();
});

test('POST /run-agent with an empty prompt is 400', async () => {
  const server = createGateway({ secret: SECRET, spawnChild: () => null, tokens: ['A'], agentFn: async () => 'x' });
  const base = await listen(server);
  const r = await fetch(base + '/run-agent', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + SECRET },
    body: JSON.stringify({ prompt: '   ' }),
  });
  const j = await r.json();
  assert.equal(r.status, 400);
  assert.equal(j.error.code, 'empty-prompt');
  server.close();
});
