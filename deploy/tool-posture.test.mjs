// deploy/tool-posture.test.mjs — offline tests for the boot tool-posture self-check (spec 007).
//
// judgeToolPosture is the pure decision core: given the init probe {tools, mcpServers} the real
// claude reports, it decides pass (no non-beans tool callable AND the beans MCP server configured)
// or fail. These encode the spike finding (a leaked shell-capable built-in must fail) and the
// 2.1.215 reality (the beans server is "pending" at init but still counts as configured; its tools
// arrive asynchronously, so the security check is offending===0, not "beans tools in the snapshot").
//
// Run: node deploy/tool-posture.test.mjs   (node:test; exits non-zero on any failure)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { judgeToolPosture, ALLOWED_MCP_PREFIX } from './tool-posture.mjs';

const beansPending = [{ name: 'beans', status: 'pending' }];
const beansConnected = [{ name: 'beans', status: 'connected' }];

test('passes when no built-in is callable and beans is configured (pending at init is fine)', () => {
  const r = judgeToolPosture({ tools: [], mcpServers: beansPending });
  assert.equal(r.ok, true);
  assert.deepEqual(r.offending, []);
  assert.equal(r.beansStatus, 'pending');
});

test('passes when beans is connected and its tools are already listed', () => {
  const r = judgeToolPosture({ tools: ['mcp__beans__read_stock'], mcpServers: beansConnected });
  assert.equal(r.ok, true);
  assert.deepEqual(r.offending, []);
});

test('fails closed when a shell-capable built-in leaked (the spike finding)', () => {
  const r = judgeToolPosture({ tools: ['Monitor'], mcpServers: beansPending });
  assert.equal(r.ok, false);
  assert.deepEqual(r.offending, ['Monitor']);
});

test('fails closed on the 2.1.215 Task family if the denylist misses them', () => {
  const r = judgeToolPosture({ tools: ['TaskCreate', 'TaskUpdate', 'ShareOnboardingGuide'], mcpServers: beansPending });
  assert.equal(r.ok, false);
  assert.deepEqual(r.offending.sort(), ['ShareOnboardingGuide', 'TaskCreate', 'TaskUpdate']);
});

test('fails when the beans MCP server is not configured at all', () => {
  const r = judgeToolPosture({ tools: [], mcpServers: [] });
  assert.equal(r.ok, false);
  assert.equal(r.beansStatus, 'absent');
});

test('fails when the beans MCP server failed to spawn', () => {
  const r = judgeToolPosture({ tools: [], mcpServers: [{ name: 'beans', status: 'failed' }] });
  assert.equal(r.ok, false);
});

test('a foreign MCP server does not satisfy the beans liveness check', () => {
  const r = judgeToolPosture({ tools: [], mcpServers: [{ name: 'other', status: 'connected' }] });
  assert.equal(r.ok, false);
  assert.equal(r.beansStatus, 'absent');
});

test('the allowed prefix is the beans namespace', () => {
  assert.equal(ALLOWED_MCP_PREFIX, 'mcp__beans__');
});
