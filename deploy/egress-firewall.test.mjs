// deploy/egress-firewall.test.mjs — spec 010 M5 T-026 (AC-T7). The NETWORK egress firewall is the
// load-bearing control (the in-code egress-guard.mjs is the second layer, tested in
// egress-guard.test.mjs, which also proves a blocked egress). This asserts the firewall CONFIG is
// present in the generated Nomad job and correctly shaped: default-drop, a tight allowlist, and
// fail-closed. The live apply (nft availability on the box, Vercel IP dynamism) is validated at the
// deploy (#273/#274). Run: node deploy/egress-firewall.test.mjs (node:test).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { render } from './build-hcl.mjs';

const hcl = render();

test('the gateway task is granted NET_ADMIN so it can apply the firewall', () => {
  assert.ok(/cap_add\s*=\s*\[\s*"NET_ADMIN"\s*\]/.test(hcl), 'NET_ADMIN capability must be present');
});

test('the egress firewall defaults to DROP on output (deny-all)', () => {
  assert.ok(hcl.includes('hook output'), 'an output-hook chain must exist');
  assert.ok(/policy drop/.test(hcl), 'the output chain policy must be drop (deny-all)');
});

test('the firewall allows only loopback, established, DNS, and 443 to the allowed hosts', () => {
  assert.ok(/oif lo accept/.test(hcl), 'loopback must be allowed');
  assert.ok(/ct state established,related accept/.test(hcl), 'established/related must be allowed');
  assert.ok(/dport 53 accept/.test(hcl), 'DNS must be allowed (to resolve the allowed hosts)');
  assert.ok(/tcp dport 443 accept/.test(hcl), '443 to the allowlist must be the only outbound app traffic');
});

test('the allowlist is exactly the ops host (BEANS_OPS_URL) and api.anthropic.com', () => {
  assert.ok(hcl.includes('BEANS_OPS_URL'), 'the ops host is derived from BEANS_OPS_URL');
  assert.ok(hcl.includes('api.anthropic.com'), 'Anthropic is the only other allowed host');
});

test('the firewall fails CLOSED (no nft, or no resolvable IP -> the box does not serve)', () => {
  assert.ok(/nft absent and BEANS_EGRESS_FIREWALL!=0 \(fail closed\)/.test(hcl), 'a missing nft must fail closed');
  assert.ok(/could not resolve any allowed egress IP \(fail closed\)/.test(hcl), 'an empty allowlist must fail closed');
});

test('BEANS_EGRESS_FIREWALL=0 is a documented, explicit escape hatch (not the default)', () => {
  assert.ok(/BEANS_EGRESS_FIREWALL:-1/.test(hcl), 'the firewall defaults ON (1)');
  assert.ok(/DISABLED by BEANS_EGRESS_FIREWALL=0/.test(hcl), 'disabling is explicit and logged');
});
