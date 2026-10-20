// deploy/beans-mcp.test.mjs — offline tests for the beans MCP tool layer (spec 007 M1).
// A fake fetch stands in for the internal operation API, so the full tool-call path is
// exercised deterministically: no network, no spawned child, no DB, no Claude token.
//
// Run: node deploy/beans-mcp.test.mjs   (node:test; exits non-zero on any failure)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  readStock, readRevenue, readProfit, readSalesSummary, readModule, businessStatus,
  registerSale, registerExpense, addStock,
  makeDispatcher, TOOLS, MODULE_IDS,
} from './beans-mcp.mjs';

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

test('dispatch: tools/list advertises exactly the M2 read surface and no commit/write tool', async () => {
  const dispatch = makeDispatcher({ config: CFG });
  const resp = await dispatch({ jsonrpc: '2.0', id: 1, method: 'tools/list' });
  const names = resp.result.tools.map((t) => t.name);
  assert.deepEqual(
    names.sort(),
    ['add_stock', 'business_status', 'cancel_last_operation', 'deactivate_product', 'read_module',
     'read_profit', 'read_revenue', 'read_sales_summary', 'read_stock', 'register_expense',
     'register_product', 'register_products_batch', 'register_sale', 'update_product_price'],
  );
  // There is NO commit/confirm tool and never will be (D-038): the write tools only PREVIEW;
  // the commit is not a model capability.
  assert.ok(!names.some((n) => n.startsWith('commit') || n.includes('confirm') || n.includes('undo')));
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

// ── M2 read surface (s-04) ────────────────────────────────────────────────────

test('no tool anywhere exposes the tenant as an argument (tenant is pinned out of band)', () => {
  for (const t of TOOLS) {
    const props = Object.keys(t.inputSchema.properties || {});
    assert.ok(!props.some((p) => /phone|tenant/i.test(p)), `${t.name} must not take a tenant arg`);
    assert.equal(t.inputSchema.additionalProperties, false, `${t.name} must be a closed schema`);
  }
});

test('read_revenue and read_profit take no arguments and lift their result key', async () => {
  const seen = {};
  const mk = (key, payload) => fakeFetch((url, opts) => {
    seen[key] = url;
    return { ok: true, status: 200, json: async () => payload };
  });
  const rev = await readRevenue({ ...CFG, fetchImpl: mk('rev', { ok: true, revenue: { revenue_usd: 12.5 } }) });
  const pro = await readProfit({ ...CFG, fetchImpl: mk('pro', { ok: true, profit: { profit_usd: 3.1 } }) });
  assert.equal(seen.rev, 'http://ops.local/internal/ops/read_revenue');
  assert.equal(seen.pro, 'http://ops.local/internal/ops/read_profit');
  assert.match(rev.content[0].text, /12\.5/);
  assert.match(pro.content[0].text, /3\.1/);
  // Only the result key is returned to the model, not the transport envelope.
  assert.ok(!/\"ok\"/.test(rev.content[0].text));
});

test('read_sales_summary sends limit in the body only when it is an integer', async () => {
  let bodyWith, bodyWithout;
  await readSalesSummary({ ...CFG, fetchImpl: fakeFetch((u, o) => { bodyWith = o.body; return { ok: true, status: 200, json: async () => ({ ok: true, sales_summary: [] }) }; }) }, { limit: 7 });
  await readSalesSummary({ ...CFG, fetchImpl: fakeFetch((u, o) => { bodyWithout = o.body; return { ok: true, status: 200, json: async () => ({ ok: true, sales_summary: [] }) }; }) }, {});
  assert.deepEqual(JSON.parse(bodyWith), { limit: 7 });
  assert.deepEqual(JSON.parse(bodyWithout), {}); // no limit -> server default, tenant still never in body
});

test('read_module sends the chosen module id in the body and lifts the module result', async () => {
  let body, url;
  const r = await readModule({ ...CFG, fetchImpl: fakeFetch((u, o) => { url = u; body = o.body; return { ok: true, status: 200, json: async () => ({ ok: true, module: { id: 'costos', label: 'Costos' } }) }; }) }, { module: 'costos' });
  assert.equal(url, 'http://ops.local/internal/ops/read_module');
  assert.deepEqual(JSON.parse(body), { module: 'costos' });
  assert.match(r.content[0].text, /costos/);
});

test('read_module enum lists exactly the eight command-center modules', () => {
  const t = TOOLS.find((x) => x.name === 'read_module');
  assert.deepEqual(
    [...t.inputSchema.properties.module.enum].sort(),
    ['caja', 'costos', 'logistica', 'produccion', 'productos', 'proveedores', 'stock', 'ventas'],
  );
  assert.deepEqual([...MODULE_IDS].sort(), [...t.inputSchema.properties.module.enum].sort());
});

test('business_status lifts the attention list and never invents (error -> is_error, not a fake list)', async () => {
  const ok = await businessStatus({ ...CFG, fetchImpl: fakeFetch(() => ({ ok: true, status: 200, json: async () => ({ ok: true, attention: [{ text: 'Stock bajo', severity: 0 }] }) })) });
  assert.match(ok.content[0].text, /Stock bajo/);
  const bad = await businessStatus({ ...CFG, fetchImpl: fakeFetch(() => ({ ok: false, status: 500, json: async () => ({ ok: false, error: { code: 'internal_error', message: 'business_status failed' } }) })) });
  assert.equal(bad.isError, true);
  assert.match(bad.content[0].text, /business_status failed/);
});

// ── M3 write-PREVIEW tools (stage, never commit) ───────────────────────────────────

test('write tools stage a preview and NEVER hand the op_token to the model', async () => {
  const fetchImpl = fakeFetch((url, opts) => ({
    ok: true, status: 200,
    json: async () => ({ ok: true, staged: true, op_token: 'SECRET-abc123',
      operation_type: 'REGISTER_SALE', summary: 'Venta: 1 × Tabla a $400 = $400' }),
  }));
  const r = await registerSale({ ...CFG, fetchImpl }, { product: 'tabla', quantity: 1, unit_amount: 400 });
  assert.equal(r.isError, undefined);
  assert.match(r.content[0].text, /Venta/);
  // The commit handle must not reach the model (defense in depth, D-040).
  assert.doesNotMatch(r.content[0].text, /SECRET-abc123/);
  assert.doesNotMatch(r.content[0].text, /op_token/);
});

test('register_sale sends product/quantity/unit_amount in the body, tenant only via header', async () => {
  let seen;
  const fetchImpl = fakeFetch((url, opts) => { seen = { url, body: opts.body, headers: opts.headers };
    return { ok: true, status: 200, json: async () => ({ ok: true, staged: true, op_token: 't', summary: 's' }) }; });
  await registerSale({ ...CFG, fetchImpl }, { product: 'tabla', quantity: 2, unit_amount: 400 });
  assert.equal(seen.url, 'http://ops.local/internal/ops/preview/register_sale');
  assert.deepEqual(JSON.parse(seen.body), { product: 'tabla', quantity: 2, unit_amount: 400 });
  assert.equal(seen.headers['x-beans-tenant'], '+5491100000001');
});

test('a clarify (no stage) comes back as the message, not a fabricated success', async () => {
  const fetchImpl = fakeFetch(() => ({ ok: true, status: 200,
    json: async () => ({ ok: true, staged: false, clarify: 'need_price', message: '¿A cuánto la vendés?' }) }));
  const r = await registerSale({ ...CFG, fetchImpl }, { product: 'tabla' });
  assert.match(r.content[0].text, /A cuánto/);
  assert.match(r.content[0].text, /need_price/);
});

test('write preview tools have no tenant argument and are closed schemas', () => {
  for (const name of ['register_sale', 'register_expense', 'add_stock']) {
    const t = TOOLS.find((x) => x.name === name);
    assert.ok(t, `${name} must exist`);
    const props = Object.keys(t.inputSchema.properties || {});
    assert.ok(!props.some((p) => /phone|tenant|op_token/i.test(p)), `${name} must not take tenant/op_token`);
    assert.equal(t.inputSchema.additionalProperties, false);
  }
});

test('dispatch routes the write tools to their impls with arguments', async () => {
  const calls = [];
  const dispatch = makeDispatcher({
    config: CFG,
    registerSaleImpl: async (_c, a) => { calls.push(['sale', a.product, a.quantity, a.unit_amount]); return { content: [{ type: 'text', text: 's' }] }; },
    registerExpenseImpl: async (_c, a) => { calls.push(['expense', a.amount, a.description]); return { content: [{ type: 'text', text: 'e' }] }; },
    addStockImpl: async (_c, a) => { calls.push(['stock', a.product, a.quantity]); return { content: [{ type: 'text', text: 'k' }] }; },
  });
  await dispatch({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'register_sale', arguments: { product: 'tabla', quantity: 1, unit_amount: 400 } } });
  await dispatch({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'register_expense', arguments: { amount: 200, description: 'café' } } });
  await dispatch({ jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'add_stock', arguments: { product: 'tabla', quantity: 10 } } });
  assert.deepEqual(calls, [['sale', 'tabla', 1, 400], ['expense', 200, 'café'], ['stock', 'tabla', 10]]);
});

test('dispatch routes each read tool to its impl and passes arguments through', async () => {
  const calls = [];
  const dispatch = makeDispatcher({
    config: CFG,
    readStockImpl: async () => { calls.push(['stock']); return { content: [{ type: 'text', text: 'stock' }] }; },
    readRevenueImpl: async () => { calls.push(['revenue']); return { content: [{ type: 'text', text: 'rev' }] }; },
    readProfitImpl: async () => { calls.push(['profit']); return { content: [{ type: 'text', text: 'pro' }] }; },
    readSalesSummaryImpl: async (_c, a) => { calls.push(['sales', a.limit]); return { content: [{ type: 'text', text: 'sales' }] }; },
    readModuleImpl: async (_c, a) => { calls.push(['module', a.module]); return { content: [{ type: 'text', text: 'module' }] }; },
    businessStatusImpl: async () => { calls.push(['status']); return { content: [{ type: 'text', text: 'status' }] }; },
  });
  await dispatch({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'read_revenue', arguments: {} } });
  await dispatch({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'read_sales_summary', arguments: { limit: 5 } } });
  await dispatch({ jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'read_module', arguments: { module: 'ventas' } } });
  await dispatch({ jsonrpc: '2.0', id: 4, method: 'tools/call', params: { name: 'business_status', arguments: {} } });
  assert.deepEqual(calls, [['revenue'], ['sales', 5], ['module', 'ventas'], ['status']]);
});
