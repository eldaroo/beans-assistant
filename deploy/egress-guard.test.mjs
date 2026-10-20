// deploy/egress-guard.test.mjs — the box egress allowlist (spec 007 M4, AC12).
// Run: node deploy/egress-guard.test.mjs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  egressAllowlist, isEgressAllowed, assertEgressAllowed, guardedFetch, verifyEgressConfig,
  ANTHROPIC_HOSTS,
} from './egress-guard.mjs';

const OPS = 'https://beans-command-center.mdlautomations.duckdns.org';

test('allowlist contains the ops host and Anthropic, nothing else implied', () => {
  const a = egressAllowlist({ opsUrl: OPS });
  assert.ok(a.has('beans-command-center.mdlautomations.duckdns.org'));
  assert.ok(a.has('api.anthropic.com'));
  assert.ok(!a.has('evil.com'));
});

test('isEgressAllowed allows the ops host, Anthropic, and a subdomain; blocks the rest', () => {
  const a = egressAllowlist({ opsUrl: OPS });
  assert.equal(isEgressAllowed(OPS + '/internal/ops/read_stock', a), true);
  assert.equal(isEgressAllowed('https://api.anthropic.com/v1/messages', a), true);
  assert.equal(isEgressAllowed('https://foo.api.anthropic.com/x', a), true); // subdomain
  assert.equal(isEgressAllowed('https://evil.com/collect', a), false);
  assert.equal(isEgressAllowed('http://169.254.169.254/latest/meta-data', a), false); // cloud metadata
});

test('assertEgressAllowed / guardedFetch fail closed on a disallowed host', async () => {
  const a = egressAllowlist({ opsUrl: OPS });
  assert.throws(() => assertEgressAllowed('https://evil.com/x', a), /EGRESS-BLOCKED/);
  let called = false;
  const gf = guardedFetch(a, async () => { called = true; return { ok: true }; });
  await assert.rejects(() => gf('https://evil.com/x'), /EGRESS-BLOCKED/);
  assert.equal(called, false); // the blocked call never reached the real fetch
  await gf(OPS + '/internal/ops/read_stock'); // the allowed call passes through
  assert.equal(called, true);
});

test('verifyEgressConfig fails closed when the ops url is missing', () => {
  assert.equal(verifyEgressConfig({ opsUrl: '' }).ok, false);
  assert.equal(verifyEgressConfig({ opsUrl: OPS }).ok, true);
});

test('Anthropic hosts are the only non-ops hosts allowed by default', () => {
  const a = egressAllowlist({ opsUrl: OPS });
  const nonOps = [...a].filter((h) => !h.includes('mdlautomations'));
  assert.deepEqual(nonOps.sort(), [...ANTHROPIC_HOSTS].sort());
});
