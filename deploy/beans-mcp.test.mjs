// deploy/beans-mcp.test.mjs — offline tests for the beans MCP tool layer (spec 007 M1).
// A fake fetch stands in for the internal operation API, so the full tool-call path is
// exercised deterministically: no network, no spawned child, no DB, no Claude token.
//
// Run: node deploy/beans-mcp.test.mjs   (node:test; exits non-zero on any failure)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readStock, makeDispatcher, TOOLS } from './beans-mcp.mjs';

const CFG = { opsUrl: 'http://ops.local', token: 'tok-123', phone: '+5491100000001' };

function fakeFetch(handler) {
  return async (url, opts) => handler(url, opts);
}

test('read_stock sends the internal token and pins the tenant via header, never the body', async () => {
  let seen;
  const fetchImpl = fakeFetch((url, opts) => {
    seen = { url, headers: opts.headers, body: opts.body };
    return { ok: true, status: 200, json: async () => ({ ok: true, stock: [{ sku: 'PCC-001', quantity: 48 }] }) };
  });
  const r = await readStock({ ...CFG, fetchImpl });
  assert.equal(seen.url, 'http://ops.local/internal/ops/read_stock');
  assert.equal(seen.headers['x-internal-token'], 'tok-123');
  assert.equal(seen.headers['x-beans-tenant'], '+5491100000001');
  assert.equal(seen.body, '{}'); // no tenant in the body
  assert.equal(r.isError, undefined);
  assert.match(r.content[0].text, /PCC-001/);
});

test('read_stock surfaces an error envelope as an error content, not a crash', async () => {
  const fetchImpl = fakeFetch(() => ({ ok: false, status: 500, json: async () => ({ ok: false, error: { code: 'internal_error', message: 'read_stock failed' } }) }));
  const r = await readStock({ ...CFG, fetchImpl });
  assert.equal(r.isError, true);
  assert.match(r.content[0].text, /read_stock failed/);
});

test('read_stock fails closed when not configured (no token/url/phone)', async () => {
  const r = await readStock({ opsUrl: '', token: '', phone: '' });
  assert.equal(r.isError, true);
});

test('read_stock reports an unreachable operation API instead of throwing', async () => {
  const fetchImpl = fakeFetch(() => { throw new Error('ECONNREFUSED'); });
  const r = await readStock({ ...CFG, fetchImpl });
  assert.equal(r.isError, true);
  assert.match(r.content[0].text, /could not reach/);
});

test('dispatch: tools/list advertises exactly read_stock and no commit tool', async () => {
  const dispatch = makeDispatcher({ config: CFG });
  const resp = await dispatch({ jsonrpc: '2.0', id: 1, method: 'tools/list' });
  const names = resp.result.tools.map((t) => t.name);
  assert.deepEqual(names, ['read_stock']);
  assert.ok(!names.some((n) => n.startsWith('commit') || n.startsWith('write')));
});

test('dispatch: tools/call read_stock runs the injected read and returns its content', async () => {
  const readStockImpl = async () => ({ content: [{ type: 'text', text: '{"stock":[{"sku":"PCC-001"}]}' }] });
  const dispatch = makeDispatcher({ readStockImpl, config: CFG });
  const resp = await dispatch({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'read_stock', arguments: {} } });
  assert.match(resp.result.content[0].text, /PCC-001/);
});

test('dispatch: an unknown tool is a JSON-RPC error, not a silent pass', async () => {
  const dispatch = makeDispatcher({ config: CFG });
  const resp = await dispatch({ jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'commit_everything' } });
  assert.ok(resp.error);
  assert.equal(resp.error.code, -32601);
});

test('dispatch: a notification gets no response', async () => {
  const dispatch = makeDispatcher({ config: CFG });
  const resp = await dispatch({ jsonrpc: '2.0', method: 'notifications/initialized' });
  assert.equal(resp, null);
});

test('TOOLS schema: read_stock takes no arguments (tenant is out of band)', () => {
  const t = TOOLS.find((x) => x.name === 'read_stock');
  assert.deepEqual(t.inputSchema.properties, {});
  assert.equal(t.inputSchema.additionalProperties, false);
});
