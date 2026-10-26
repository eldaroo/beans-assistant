// deploy/injection-corpus.test.mjs — spec 010 M5 T-024 (AC9, AC-T5; ports spec 007 AC9), the
// GATEWAY half: "an attempt to invoke a built-in tool is denied." The WEB half (an injected write
// stays ungrounded and never auto-posts) is web/scripts/t-injection-corpus.mts. Run:
//   node deploy/injection-corpus.test.mjs   (node:test)
//
// The attack surface a tool-use agent reopens: a prompt-injection (in tenant text a read tool
// returns, or in the operator message) that makes the model REACH for a shell/file/network
// built-in. The posture self-check is fail-closed on that: any callable tool outside the beans MCP
// namespace fails the gate, so the box never serves a configuration where a hijacked model could
// run a built-in. This drives a corpus of the built-ins an injection would reach for.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { judgeToolPosture } from './tool-posture.mjs';

const beansConnected = [{ name: 'beans', status: 'connected' }];

// The built-ins a prompt-injection would try to reach to exfiltrate or act (shell, file, net, task).
const INJECTION_TARGETS = ['Bash', 'BashOutput', 'Write', 'Read', 'Edit', 'WebFetch', 'WebSearch', 'Task', 'TaskCreate', 'Monitor'];

for (const tool of INJECTION_TARGETS) {
  test(`an injection that reaches the built-in ${tool} is denied (posture fails closed)`, () => {
    const r = judgeToolPosture({ tools: [tool], mcpServers: beansConnected });
    assert.equal(r.ok, false, `${tool} must not pass the posture gate`);
    assert.deepEqual(r.offending, [tool]);
  });
}

test('a built-in smuggled alongside the beans tools still fails the gate', () => {
  const r = judgeToolPosture({ tools: ['mcp__beans__read_stock', 'Bash'], mcpServers: beansConnected });
  assert.equal(r.ok, false);
  assert.deepEqual(r.offending, ['Bash']);
});

test('only the beans MCP tools pass (the clean injection baseline)', () => {
  const r = judgeToolPosture({ tools: ['mcp__beans__read_stock', 'mcp__beans__register_sale'], mcpServers: beansConnected });
  assert.equal(r.ok, true);
  assert.deepEqual(r.offending, []);
});
