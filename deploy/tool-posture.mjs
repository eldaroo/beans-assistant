// Boot tool-posture self-check for the native-tool-use gateway (spec 007, D-035 corrected).
//
// WHY THIS EXISTS (spike finding, 2026-10-19): `--allowedTools mcp__beans__*` is an
// auto-APPROVE grant, NOT an exclusive allowlist. In headless `-p` with no TTY, an MCP
// tool on the allowlist auto-approves and runs WITHOUT --dangerously-skip-permissions
// (good, the approach works), but every OTHER tool Claude Code loads stays callable unless
// it is on `--disallowedTools`. The spike proved a model could reach `Monitor` (a
// shell-capable built-in) that a hand-maintained denylist had missed. A static denylist is
// fragile: a future claude version adds a tool and the list silently misses it.
//
// The robust control is a POSITIVE-IDENTITY check on the actually-callable tool set: at boot,
// probe the real `claude` with the intended argv, read the INIT `tools` array it reports, and
// refuse to serve unless that set is exactly the beans MCP tools and nothing else. Fail closed.
import { spawn } from 'node:child_process';

// Tools the gateway intends to expose. Only names matching this prefix may be callable.
export const ALLOWED_MCP_PREFIX = 'mcp__beans__';

// Probe the real claude binary with the gateway's intended argv and return the INIT tool set.
// We only need the first `{"type":"system","subtype":"init","tools":[...]}` line, so we read
// stdout until that event arrives, then kill the child. No model turn is spent.
export function probeCallableTools({
  claudeBin = process.env.CLAUDE_BIN || 'claude',
  mcpConfig,
  allowedTools = [ALLOWED_MCP_PREFIX + '*'],
  disallowedTools = [],
  cwd,
  timeoutMs = 20000,
} = {}) {
  return new Promise((resolve, reject) => {
    const args = [
      '-p', 'ok',
      '--output-format', 'stream-json',
      '--verbose',
      '--max-turns', '1',
      '--allowedTools', ...allowedTools,
    ];
    if (disallowedTools.length) args.push('--disallowedTools', ...disallowedTools);
    if (mcpConfig) args.push('--mcp-config', mcpConfig, '--strict-mcp-config');

    let child;
    try {
      child = spawn(claudeBin, args, { cwd, stdio: ['ignore', 'pipe', 'ignore'] });
    } catch (e) {
      reject(new Error('probe spawn failed: ' + e.message));
      return;
    }

    let buf = '';
    let settled = false;
    const done = (fn, v) => { if (settled) return; settled = true; clearTimeout(timer); try { child.kill(); } catch {} fn(v); };
    const timer = setTimeout(() => done(reject, new Error('probe timeout: no init event in ' + timeoutMs + 'ms')), timeoutMs);

    child.on('error', (e) => done(reject, new Error('probe error: ' + e.message)));
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      buf += chunk;
      let idx;
      while ((idx = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 1);
        if (!line) continue;
        let e;
        try { e = JSON.parse(line); } catch { continue; }
        if (e && e.type === 'system' && e.subtype === 'init' && Array.isArray(e.tools)) {
          done(resolve, {
            tools: e.tools.slice(),
            mcpServers: Array.isArray(e.mcp_servers) ? e.mcp_servers.slice() : [],
          });
          return;
        }
      }
    });
    child.on('exit', () => {
      if (!settled) done(reject, new Error('probe exited before init event'));
    });
  });
}

// Decide pass/fail from an init probe {tools, mcpServers} (a bare tools array is accepted too).
//
// SECURITY (the hard guarantee): every callable built-in must be disallowed, so the only tool a
// hijacked model can reach is a beans MCP tool. That is `offending.length === 0`: no tool in the
// init `tools` array falls outside the allowed MCP prefix.
//
// LIVENESS: the beans MCP server connects ASYNCHRONOUSLY. On claude 2.1.215 the init event fires
// while it is still "pending", so its tools are NOT in the init snapshot yet (they become callable
// mid-turn, verified live). Requiring beans tools in the init array would wrongly fail there, so
// liveness is "beans is configured and not failed" (claude parsed the config and is connecting it),
// not "its tools are already listed". The real end-to-end read is proven by the live loop.
export function judgeToolPosture(probe, { allowedPrefix = ALLOWED_MCP_PREFIX } = {}) {
  const tools = Array.isArray(probe) ? probe : (probe && probe.tools) || [];
  const mcpServers = Array.isArray(probe) ? [] : (probe && probe.mcpServers) || [];
  const offending = tools.filter((t) => !String(t).startsWith(allowedPrefix));
  const beansTools = tools.filter((t) => String(t).startsWith(allowedPrefix));
  const beans = mcpServers.find((s) => s && s.name === 'beans');
  const beansConfigured = !!beans && beans.status !== 'failed' && beans.status !== 'error';
  return {
    ok: offending.length === 0 && beansConfigured,
    callable: tools,
    beansTools,
    offending,
    mcpServers,
    beansStatus: beans ? beans.status : 'absent',
  };
}

// Full self-check: probe the real claude and judge. Resolves the judge verdict object.
export async function verifyToolPosture(opts = {}) {
  const probe = await probeCallableTools(opts);
  return judgeToolPosture(probe, opts);
}

// CLI entry: node tool-posture.mjs --mcp-config <path> [--disallow a b c]. Exit 0 on pass,
// 1 on a leak (fail closed), 2 on a probe error. The gateway entrypoint calls this at boot.
async function main(argv) {
  const get = (flag) => {
    const i = argv.indexOf(flag);
    if (i < 0) return undefined;
    const out = [];
    for (let j = i + 1; j < argv.length && !argv[j].startsWith('--'); j++) out.push(argv[j]);
    return out;
  };
  const mcpConfig = (get('--mcp-config') || [])[0];
  const disallowedTools = get('--disallow') || [];
  const allowedTools = get('--allow') || [ALLOWED_MCP_PREFIX + '*'];
  try {
    const r = await verifyToolPosture({ mcpConfig, disallowedTools, allowedTools });
    if (r.ok) {
      console.log('TOOL-POSTURE-OK callable=' + JSON.stringify(r.callable));
      process.exit(0);
    }
    console.error('TOOL-POSTURE-FAIL offending=' + JSON.stringify(r.offending) + ' callable=' + JSON.stringify(r.callable));
    process.exit(1);
  } catch (e) {
    console.error('TOOL-POSTURE-PROBE-ERROR ' + e.message);
    process.exit(2);
  }
}

// Run main only when invoked directly, not when imported.
import { fileURLToPath } from 'node:url';
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main(process.argv.slice(2));
}
