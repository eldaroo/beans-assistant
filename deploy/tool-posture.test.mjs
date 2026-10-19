// deploy/tool-posture.test.mjs — offline tests for the boot tool-posture self-check (spec 007).
//
// judgeToolPosture is the pure decision core: given the tool set the real claude reports at
// INIT, it decides pass (only beans MCP tools callable) or fail (anything else leaked). These
// tests encode the spike finding (2026-10-19) as a regression: a leaked shell-capable built-in
// like Monitor MUST fail the posture, and the exact-identity set MUST pass.
//
// Run: node deploy/tool-posture.test.mjs   (node:test; exits non-zero on any failure)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { judgeToolPosture, ALLOWED_MCP_PREFIX } from './tool-posture.mjs';

test('passes when only beans MCP tools are callable', () => {
  const r = judgeToolPosture(['mcp__beans__read_stock', 'mcp__beans__preview_sale']);
  assert.equal(r.ok, true);
  assert.deepEqual(r.offending, []);
  assert.equal(r.beansTools.length, 2);
});

test('fails closed when a shell-capable built-in leaked (the spike finding)', () => {
  // The exact leak the negative spike surfaced: an incomplete denylist left Monitor callable.
  const r = judgeToolPosture(['mcp__beans__read_stock', 'Monitor']);
  assert.equal(r.ok, false);
  assert.deepEqual(r.offending, ['Monitor']);
});

test('fails when any non-beans tool is present, even a seemingly benign one', () => {
  const r = judgeToolPosture(['mcp__beans__read_stock', 'ToolSearch', 'Workflow']);
  assert.equal(r.ok, false);
  assert.deepEqual(r.offending.sort(), ['ToolSearch', 'Workflow']);
});

test('fails when NO beans tool is callable (the server is not actually wired)', () => {
  const r = judgeToolPosture([]);
  assert.equal(r.ok, false);
  assert.equal(r.beansTools.length, 0);
});

test('a foreign MCP server does not pass as a beans tool', () => {
  const r = judgeToolPosture(['mcp__other__do_thing']);
  assert.equal(r.ok, false);
  assert.deepEqual(r.offending, ['mcp__other__do_thing']);
});

test('the allowed prefix is the beans namespace', () => {
  assert.equal(ALLOWED_MCP_PREFIX, 'mcp__beans__');
});
