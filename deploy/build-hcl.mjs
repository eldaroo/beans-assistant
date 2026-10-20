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
const INDENT = '          '; // 10 spaces; the <<-EOJS closing marker sits at 8, leaving 2 after strip

// Each marker is replaced by the indented contents of its source module. gateway.mjs imports its
// siblings, so every file gateway.mjs needs at runtime ships as its own /local/*.mjs via the
// template stanzas in beans-ai.nomad.tmpl.hcl.
const EMBEDS = {
  '@@GATEWAY_MJS@@': 'gateway.mjs',
  '@@TOKEN_POOL_MJS@@': 'token-pool.mjs',
};

export function render() {
  let out = readFileSync(join(HERE, 'beans-ai.nomad.tmpl.hcl'), 'utf8');
  for (const [marker, file] of Object.entries(EMBEDS)) {
    if (!out.includes(marker)) throw new Error('template missing ' + marker);
    const src = readFileSync(join(HERE, file), 'utf8');
    const embedded = src
      .replace(/\n+$/, '') // drop trailing blank lines so the heredoc is tight
      .split('\n')
      .map((line) => (line.length ? INDENT + line : ''))
      .join('\n');
    const markerLine = new RegExp('^[ \\t]*' + marker + '[ \\t]*$', 'm');
    if (!markerLine.test(out)) throw new Error('no standalone ' + marker + ' line in template');
    out = out.replace(markerLine, embedded);
  }
  return out;
}

const isMain = (process.argv[1] || '').endsWith('build-hcl.mjs');
if (isMain) {
  const out = render();
  writeFileSync(join(HERE, 'beans-ai.nomad.hcl'), out);
  console.log('[build-hcl] wrote deploy/beans-ai.nomad.hcl (' + out.length + ' bytes)');
}
