// deploy/test.mjs — node-harness entry point for `bin/qie develop gate` (runs `node test.mjs`).
// Runs the beans-ai gateway suite (gateway.test.mjs) and the HCL sync/structural checks it
// carries. The develop gate treats this harness as PASS only on a zero exit AND the literal
// sentinel "all checks passed." in output, so we emit it when node:test leaves exitCode clean.
import './gateway.test.mjs';
import './tool-posture.test.mjs';
import './beans-mcp.test.mjs';
import './token-pool.test.mjs';
import './agent-mode.test.mjs';

process.on('exit', (code) => {
  if (!process.exitCode && !code) console.log('all checks passed.');
});
