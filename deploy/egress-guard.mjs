// Egress allowlist for the native-tool-use gateway box (spec 007 M4, AC12).
//
// The box must only ever reach two places: the internal operation API (the ONLY place the
// tools call) and Anthropic (the model). Anything else — a data-exfiltration callback a
// hijacked model or a compromised dependency might attempt — must be refused. The hard,
// network-level enforcement is the Nomad job's egress firewall (infra, deployed in M6); this
// module is the application-level allowlist + a boot assertion that the allowlist is sane and
// a guarded-fetch wrapper the outbound call paths use, so the control is testable and fails
// closed in code as well as at the firewall.
import process from 'node:process';

// Anthropic API hosts the model traffic legitimately reaches.
export const ANTHROPIC_HOSTS = ['api.anthropic.com', 'anthropic.com'];

function _host(u) {
  try { return new URL(u).hostname.toLowerCase(); } catch { return ''; }
}

// Build the allowlist of hostnames from the ops API url plus Anthropic.
export function egressAllowlist({ opsUrl = process.env.BEANS_OPS_URL, extra = [] } = {}) {
  const hosts = new Set(ANTHROPIC_HOSTS.map((h) => h.toLowerCase()));
  const opsHost = _host(opsUrl);
  if (opsHost) hosts.add(opsHost);
  for (const e of extra) { const h = (e || '').toLowerCase(); if (h) hosts.add(h); }
  return hosts;
}

// True iff `url`'s host is on the allowlist (exact host or a subdomain of an allowed host).
export function isEgressAllowed(url, allowlist) {
  const host = _host(url);
  if (!host) return false;
  for (const a of allowlist) {
    if (host === a || host.endsWith('.' + a)) return true;
  }
  return false;
}

// Throw on a disallowed host (the fetch-guard). Fail closed.
export function assertEgressAllowed(url, allowlist) {
  if (!isEgressAllowed(url, allowlist)) {
    throw new Error('EGRESS-BLOCKED ' + (_host(url) || url));
  }
}

// Wrap a fetch so every outbound call is checked against the allowlist first.
export function guardedFetch(allowlist, fetchImpl = fetch) {
  return async function (url, opts) {
    assertEgressAllowed(url, allowlist); // throws -> rejected promise (fail closed)
    return fetchImpl(url, opts);
  };
}

// Boot check: the allowlist must contain the ops host AND Anthropic, or we refuse to serve
// (a box that cannot name where it may talk is misconfigured). Returns {ok, allowlist, reason}.
export function verifyEgressConfig({ opsUrl = process.env.BEANS_OPS_URL } = {}) {
  const allowlist = egressAllowlist({ opsUrl });
  const opsHost = _host(opsUrl);
  if (!opsHost) return { ok: false, allowlist: [...allowlist], reason: 'ops-url-missing-or-invalid' };
  const hasAnthropic = ANTHROPIC_HOSTS.some((h) => allowlist.has(h));
  if (!hasAnthropic) return { ok: false, allowlist: [...allowlist], reason: 'anthropic-host-absent' };
  return { ok: true, allowlist: [...allowlist], reason: null };
}

// CLI: node egress-guard.mjs. Exit 0 if the egress config is sane, 1 otherwise (fail closed).
function main() {
  const r = verifyEgressConfig();
  if (r.ok) {
    console.log('EGRESS-OK allow=' + JSON.stringify(r.allowlist));
    process.exit(0);
  }
  console.error('EGRESS-FAIL reason=' + r.reason + ' allow=' + JSON.stringify(r.allowlist));
  process.exit(1);
}

import { fileURLToPath } from 'node:url';
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main();
}
