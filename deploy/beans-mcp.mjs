// Beans MCP server (spec 007, the tool layer). Line-delimited JSON-RPC 2.0 over stdio.
//
// These tools hold NO database credentials (D-036). Each calls the FastAPI internal
// operation API with the internal service token and the tenant pinned OUT OF BAND:
// the gateway injects BEANS_TENANT_PHONE per request, the tool sends it as the
// x-beans-tenant header, and the model never sees or sets it (D-037). There is no
// commit tool and never will be; writes are two-phase previews that land in M3+ (D-038).
//
// M1 ships one read tool, read_stock, so the model -> MCP -> internal API -> DB path is
// real. The HTTP call and the message dispatch are exported so they unit-test with an
// injected fetch, no network and no spawned child.
import process from 'node:process';

export const TOOLS = [
  {
    name: 'read_stock',
    description:
      'Read the current stock (units on hand per product) for the business. Takes no arguments; ' +
      'the business is fixed for this session. Use it when the owner asks how much of something is left.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
];

// Call the internal read_stock endpoint. Returns an MCP tool-result content object.
// Never throws for an operational failure: it returns an is_error content so the model
// can tell the owner something went wrong instead of the loop crashing.
export async function readStock({ opsUrl, token, phone, fetchImpl = fetch } = {}) {
  if (!opsUrl || !token || !phone) {
    return { content: [{ type: 'text', text: 'read_stock not configured (missing ops url, token, or tenant).' }], isError: true };
  }
  let res;
  try {
    res = await fetchImpl(opsUrl.replace(/\/$/, '') + '/internal/ops/read_stock', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-internal-token': token,
        'x-beans-tenant': phone,
      },
      body: '{}',
    });
  } catch (e) {
    return { content: [{ type: 'text', text: 'read_stock could not reach the operation API: ' + e.message }], isError: true };
  }
  let body;
  try { body = await res.json(); } catch { body = null; }
  if (!res.ok || !body || body.ok !== true) {
    const msg = (body && body.error && body.error.message) || ('read_stock failed (HTTP ' + res.status + ')');
    return { content: [{ type: 'text', text: msg }], isError: true };
  }
  return { content: [{ type: 'text', text: JSON.stringify({ stock: body.stock }) }] };
}

// Build a JSON-RPC dispatcher. `readStockImpl` is injectable for tests.
export function makeDispatcher({ readStockImpl = readStock, config = {} } = {}) {
  return async function dispatch(msg) {
    const { id, method, params } = msg || {};
    if (method === 'initialize') {
      const pv = (params && params.protocolVersion) || '2024-11-05';
      return { jsonrpc: '2.0', id, result: { protocolVersion: pv, capabilities: { tools: {} }, serverInfo: { name: 'beans', version: '0.1.0' } } };
    }
    if (method && method.startsWith('notifications/')) return null; // notifications get no response
    if (method === 'tools/list') {
      return { jsonrpc: '2.0', id, result: { tools: TOOLS } };
    }
    if (method === 'tools/call') {
      const name = params && params.name;
      if (name === 'read_stock') {
        const r = await readStockImpl({ opsUrl: config.opsUrl, token: config.token, phone: config.phone });
        return { jsonrpc: '2.0', id, result: r };
      }
      return { jsonrpc: '2.0', id, error: { code: -32601, message: 'unknown tool ' + name } };
    }
    if (id !== undefined && id !== null) return { jsonrpc: '2.0', id, result: {} };
    return null;
  };
}

// stdio main loop: read line-delimited JSON-RPC, dispatch, write responses.
function main() {
  const config = {
    opsUrl: process.env.BEANS_OPS_URL,
    token: process.env.INTERNAL_SERVICE_TOKEN,
    phone: process.env.BEANS_TENANT_PHONE,
  };
  const dispatch = makeDispatcher({ config });
  const send = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');
  let buf = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => {
    buf += chunk;
    let idx;
    while ((idx = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (!line) continue;
      let msg;
      try { msg = JSON.parse(line); } catch { continue; }
      Promise.resolve(dispatch(msg)).then((resp) => { if (resp) send(resp); });
    }
  });
}

import { fileURLToPath } from 'node:url';
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main();
}
