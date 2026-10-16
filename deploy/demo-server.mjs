// deploy/demo-server.mjs — stands up the REAL beans-ai gateway on 127.0.0.1 for the spec 005
// demonstration, with the leaf `claude` call stubbed (we have no subscription token in-run).
//
// Everything except the model leaf is real: the HTTP server, bearer auth, the warm child pool,
// the lease/dispose/replace cycle, the stream-json parsing, the /run envelope. The injected
// child is a deterministic Timonel router/read classifier so the demonstration shows real
// routing behavior end to end through the Python ChatGateway -> JsonOutputParser path.

import { EventEmitter } from 'node:events';
import { createGateway } from './gateway.mjs';

// Keyword classifier standing in for Claude. Returns the real router shape (IntentClassification:
// intent WRITE_OPERATION carries a separate operation_type), so the demonstration matches the
// router vocabulary and the parity fixtures.
function classify(text) {
  const t = text.toLowerCase();
  if (/\bhola\b|buenas|buenos dias|qué tal/.test(t)) return { intent: 'GREETING', confidence: 0.98 };
  if (/cu[áa]nt|factur|gananci|revenue|cu[áa]ntas .*tengo/.test(t)) return { intent: 'READ_ANALYTICS', confidence: 0.92 };
  if (/vend[ií]|cobr[ée]|me pagaron|seña/.test(t)) return { intent: 'WRITE_OPERATION', operation_type: 'REGISTER_SALE', confidence: 0.95 };
  if (/pagu[ée]|compr[ée]|gast[ée]/.test(t)) return { intent: 'WRITE_OPERATION', operation_type: 'REGISTER_EXPENSE', confidence: 0.93 };
  if (/agreg|entraron|sum[áa]|a[ñn]ad/.test(t)) return { intent: 'WRITE_OPERATION', operation_type: 'ADD_STOCK', confidence: 0.9 };
  if (/stock|tengo|inventario/.test(t)) return { intent: 'READ_ANALYTICS', confidence: 0.9 };
  return { intent: 'AMBIGUOUS', confidence: 0.4 };
}

function fakeClaudeChild() {
  const child = new EventEmitter();
  let written = '';
  child.stdout = new EventEmitter();
  child.stdin = {
    destroyed: false,
    write(chunk) {
      written += chunk;
      return true;
    },
    end() {
      setTimeout(() => {
        let text = '';
        try {
          const msg = JSON.parse(written.trim().split('\n').pop());
          text = msg.message.content.map((b) => b.text || '').join('');
        } catch {}
        const json = classify(text);
        const result = JSON.stringify(json);
        child.stdout.emit('data', Buffer.from(JSON.stringify({ type: 'result', subtype: 'success', result }) + '\n'));
        child.stdout.emit('end');
        child.emit('exit', 0);
      }, 2);
    },
  };
  child.kill = () => {};
  return child;
}

const secret = process.env.BEANS_AI_SHARED_SECRET || 'demo-secret';
const server = createGateway({ secret, poolTarget: 2, spawnChild: fakeClaudeChild });
server.listen(Number(process.env.DEMO_PORT || 0), '127.0.0.1', () => {
  const { port } = server.address();
  // The driver reads this line to learn the port.
  console.log('DEMO_GATEWAY_READY ' + port);
});
