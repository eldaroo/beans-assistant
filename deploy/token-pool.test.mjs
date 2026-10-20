// deploy/token-pool.test.mjs — offline tests for subscription-token rotation (spec 007).
// No real claude, no real token: resolveRun runs with an injected oneShotFn whose reply depends
// on the active token, so the bench/rotate/retry orchestration is exercised deterministically.
//
// Run: node deploy/token-pool.test.mjs   (node:test; exits non-zero on any failure)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  detectExhaustion,
  cooldownReset,
  allExhaustedMessage,
  parseTokens,
  TokenPool,
  childSpawnEnv,
} from './token-pool.mjs';
import { resolveRun, ChildPool } from './gateway.mjs';

const LIMIT = 'Claude AI usage limit reached|1799999999';

// A ChildPool with no warm children, so resolveRun always falls to the injected oneShotFn.
function emptyPool() {
  return new ChildPool({ poolTarget: 0, spawnChild: () => null });
}

// ── Pure detection ──────────────────────────────────────────────────────────
test('detectExhaustion parses the machine epoch form', () => {
  const r = detectExhaustion('Claude AI usage limit reached|1799999999');
  assert.equal(r.exhausted, true);
  assert.ok(r.resetAt instanceof Date);
});

test('detectExhaustion matches human phrasings with no reset', () => {
  assert.equal(detectExhaustion('You have reached your usage limit.').exhausted, true);
  assert.equal(detectExhaustion('weekly limit reached').exhausted, true);
});

test('detectExhaustion is false for a normal answer', () => {
  assert.equal(detectExhaustion('{"intent":"READ"}').exhausted, false);
  assert.equal(detectExhaustion('').exhausted, false);
});

// ── parseTokens ───────────────────────────────────────────────────────────────
test('parseTokens reads a JSON array, then the single, deduped, order preserved', () => {
  const toks = parseTokens({ CLAUDE_CODE_OAUTH_TOKENS: '["a","b"]', CLAUDE_CODE_OAUTH_TOKEN: 'a' });
  assert.deepEqual(toks, ['a', 'b']); // 'a' not duplicated
});

test('parseTokens reads a comma/newline list and numbered back-compat', () => {
  assert.deepEqual(parseTokens({ CLAUDE_CODE_OAUTH_TOKENS: 'x, y\nz' }), ['x', 'y', 'z']);
  assert.deepEqual(parseTokens({ CLAUDE_CODE_OAUTH_TOKEN: 'p', CLAUDE_CODE_OAUTH_TOKEN_2: 'q' }), ['p', 'q']);
});

// ── TokenPool ───────────────────────────────────────────────────────────────
test('TokenPool active is the first healthy token; bench moves to the next', () => {
  const p = new TokenPool(['A', 'B']);
  assert.equal(p.active(), 'A');
  p.bench('A', cooldownReset());
  assert.equal(p.active(), 'B');
  assert.equal(p.allBenched(), false);
  p.bench('B', cooldownReset());
  assert.equal(p.active(), null);
  assert.equal(p.allBenched(), true);
  assert.ok(p.earliestReset() instanceof Date);
});

test('childSpawnEnv overrides the token, or leaves env untouched when none', () => {
  assert.equal(childSpawnEnv({ X: '1' }, 'tok-B').CLAUDE_CODE_OAUTH_TOKEN, 'tok-B');
  assert.equal(childSpawnEnv({ X: '1' }, null).CLAUDE_CODE_OAUTH_TOKEN, undefined);
});

// ── Rotation orchestration (resolveRun) ───────────────────────────────────────
test('resolveRun rotates past an exhausted account to a healthy one and benches the first', async () => {
  const tokenPool = new TokenPool(['A', 'B']);
  // Account A is at its limit; B answers.
  const oneShotFn = async (_text, { token }) => (token === 'A' ? LIMIT : '{"ok":"from-B"}');
  const { text } = await resolveRun(emptyPool(), { system: '', prompt: 'hola' }, { tokenPool, oneShotFn });
  assert.equal(text, '{"ok":"from-B"}');
  assert.equal(tokenPool.active(), 'B'); // A benched, B now active
});

test('resolveRun throws the honest all-exhausted message when every account is at its limit', async () => {
  const tokenPool = new TokenPool(['A', 'B']);
  const oneShotFn = async () => LIMIT; // both accounts limited
  await assert.rejects(
    resolveRun(emptyPool(), { system: '', prompt: 'hola' }, { tokenPool, oneShotFn }),
    /limite de uso/
  );
  assert.equal(tokenPool.allBenched(), true);
});

test('resolveRun with a single token does not rotate (back-compat passthrough)', async () => {
  const tokenPool = new TokenPool(['A']);
  const oneShotFn = async () => 'plain answer';
  const { text } = await resolveRun(emptyPool(), { system: '', prompt: 'hola' }, { tokenPool, oneShotFn });
  assert.equal(text, 'plain answer');
});

test('allExhaustedMessage names the reset when known', () => {
  const msg = allExhaustedMessage(new Date('2026-01-01T00:00:00Z'));
  assert.match(msg, /2026-01-01/);
});
