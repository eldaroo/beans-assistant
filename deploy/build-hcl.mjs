// deploy/build-hcl.mjs — generate deploy/beans-ai.nomad.hcl from the template + gateway.mjs.
//
// Single source of truth: deploy/gateway.mjs is the gateway; deploy/beans-ai.nomad.tmpl.hcl is
// the job shell with an @@GATEWAY_MJS@@ marker. This embeds the gateway into the marker's
// indented heredoc so the box runs exactly the code the tests exercise. Run after editing either:
//   node deploy/build-hcl.mjs
// gateway.test.mjs calls render() and asserts the committed .hcl matches, so drift is caught.

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const MARKER = '@@GATEWAY_MJS@@';
const INDENT = '          '; // 10 spaces; the <<-EOJS closing marker sits at 8, leaving 2 after strip

export function render() {
  const tmpl = readFileSync(join(HERE, 'beans-ai.nomad.tmpl.hcl'), 'utf8');
  const gateway = readFileSync(join(HERE, 'gateway.mjs'), 'utf8');
  if (!tmpl.includes(MARKER)) throw new Error('template missing ' + MARKER);
  const embedded = gateway
    .replace(/\n+$/, '') // drop trailing blank lines so the heredoc is tight
    .split('\n')
    .map((line) => (line.length ? INDENT + line : ''))
    .join('\n');
  // Replace the marker line (the marker must be alone on its line, ignoring surrounding space).
  const markerLine = new RegExp('^[ \\t]*' + MARKER + '[ \\t]*$', 'm');
  if (!markerLine.test(tmpl)) throw new Error('no standalone ' + MARKER + ' line in template');
  return tmpl.replace(markerLine, embedded);
}

const isMain = (process.argv[1] || '').endsWith('build-hcl.mjs');
if (isMain) {
  const out = render();
  writeFileSync(join(HERE, 'beans-ai.nomad.hcl'), out);
  console.log('[build-hcl] wrote deploy/beans-ai.nomad.hcl (' + out.length + ' bytes)');
}
