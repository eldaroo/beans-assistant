// deploy/posture-argv.test.mjs — spec 010 M5 T-025 (AC-T8). The boot tool-posture self-check must
// validate the IDENTICAL production argv that serves a real turn, skip-permissions must be absent,
// and one child per request must be disposed. Run: node deploy/posture-argv.test.mjs (node:test).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { buildAgentArgs, agentFlags, argvSkipsPermissions, runAgentTurn } from './gateway.mjs';

test('the production argv carries the exact shared tool-governance flags (no drift)', () => {
  const mcp = '/local/mcp-beans.json';
  const argv = buildAgentArgs({ mcpConfig: mcp });
  const flags = agentFlags(mcp);
  // agentFlags is the ONE source of tool governance; it appears verbatim as a contiguous run in
  // the production argv, so the posture self-check (which probes with the same allowed/disallowed
  // set + strict-mcp-config) validates exactly what a real turn runs. A future edit that forks the
  // two would break this assertion.
  assert.ok(argv.join(' ').includes(flags.join(' ')), 'agentFlags must appear verbatim in the production argv');
  assert.ok(argv.includes('--allowedTools'));
  assert.ok(argv.includes('mcp__beans__*'));
  assert.ok(argv.includes('--strict-mcp-config'));
  // The disallow list is the full built-in denylist, same constant the self-check probes with.
  assert.ok(argv.includes('--disallowedTools'));
  assert.ok(argv.includes('Bash') && argv.includes('Monitor') && argv.includes('Task'));
});

test('the production argv NEVER skips permissions (the headless auto-deny safety model)', () => {
  assert.equal(argvSkipsPermissions(buildAgentArgs({})), false);
  assert.equal(argvSkipsPermissions(buildAgentArgs({ system: 'sys', maxTurns: 6 })), false);
});

test('argvSkipsPermissions detects the flag when present (the guard is real, not vacuous)', () => {
  assert.equal(argvSkipsPermissions(['-p', '--dangerously-skip-permissions']), true);
  assert.equal(argvSkipsPermissions(['-p', '--verbose']), false);
});

test('exactly one child is spawned per request and it is disposed after the turn', async () => {
  let spawned = 0;
  let killed = 0;
  const spawnChild = () => {
    spawned++;
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stdin = {
      write() {},
      end() {
        setTimeout(() => {
          child.stdout.emit('data', Buffer.from(JSON.stringify({ type: 'result', subtype: 'success', result: 'ok', is_error: false }) + '\n'));
          child.stdout.emit('end');
          child.emit('exit', 0);
        }, 1);
      },
    };
    child.kill = () => { killed++; };
    return child;
  };
  const text = await runAgentTurn('hola', { spawnChild });
  assert.equal(text, 'ok');
  assert.equal(spawned, 1, 'exactly one child per request');
  assert.ok(killed >= 1, 'the child is disposed (killed) after the turn resolves');
});
