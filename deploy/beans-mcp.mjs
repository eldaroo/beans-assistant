// Beans MCP server (spec 007, the tool layer). Line-delimited JSON-RPC 2.0 over stdio.
//
// These tools hold NO database credentials (D-036). Each calls the Next.js internal
// operation API (spec 010: BEANS_OPS_URL repointed from the dead FastAPI to the Next app,
// e.g. https://<app>/api, so a tool path like /internal/ops/read_stock resolves to
// https://<app>/api/internal/ops/read_stock) with the internal service token and the tenant
// pinned OUT OF BAND: the gateway injects BEANS_TENANT_PHONE per request, the tool sends it as
// the x-beans-tenant header, and the model never sees or sets it (D-037). There is no commit
// tool and never will be; writes are two-phase previews that land in M3+ (D-038).
//
// M1 shipped one read tool (read_stock). M2 adds the rest of the read surface (s-04):
// revenue, profit, sales summary, the eight command-center module snapshots, and a
// business_status tool that reads the one existing attention aggregation (AC6). Every
// tool argument here is a non-tenant parameter (a limit, a module id); the tenant is
// never a tool argument. The HTTP call and the message dispatch are exported so they
// unit-test with an injected fetch, no network and no spawned child.
import process from 'node:process';
import { egressAllowlist, isEgressAllowed } from './egress-guard.mjs';

// The eight command-center modules, by their registry ids. read_module takes one of
// these so the owner can ask about a single domain ("¿cómo van los costos?"); the set
// is fixed and model-closed (additionalProperties:false) so a hallucinated module id is
// a tool error, never a silent wrong read.
export const MODULE_IDS = [
  'caja', 'productos', 'stock', 'ventas', 'costos', 'produccion', 'logistica', 'proveedores',
];

export const TOOLS = [
  {
    name: 'read_stock',
    description:
      'Read the current stock (units on hand per product) for the business. Takes no arguments; ' +
      'the business is fixed for this session. Use it when the owner asks how much of something is left.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'read_revenue',
    description:
      'Read the business total revenue (ingresos). Takes no arguments. Use it when the owner asks ' +
      'how much the business has sold or billed in total.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'read_profit',
    description:
      'Read the business profit (ganancia). Takes no arguments. Use it when the owner asks how much ' +
      'the business is earning or netting.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'read_sales_summary',
    description:
      'Read a day-by-day summary of recent paid sales (count and revenue per day). Optional "limit" ' +
      'is how many recent days to include (1 to 50, default 10). Use it when the owner asks how sales ' +
      'have been going lately.',
    inputSchema: {
      type: 'object',
      properties: { limit: { type: 'integer', minimum: 1, maximum: 50 } },
      additionalProperties: false,
    },
  },
  {
    name: 'read_module',
    description:
      'Read one command-center module\'s current headline and anything in it that needs attention. ' +
      '"module" is one of: caja (Resultado/net), productos, stock, ventas, costos, produccion, ' +
      'logistica, proveedores. Use it when the owner asks about one specific area of the business.',
    inputSchema: {
      type: 'object',
      properties: { module: { type: 'string', enum: MODULE_IDS } },
      required: ['module'],
      additionalProperties: false,
    },
  },
  {
    name: 'business_status',
    description:
      'Read the one prioritized "what needs attention today" list across the whole business (overdue ' +
      'arrivals, overdue supplier check-ins, pending customs). Takes no arguments. Use it when the owner asks how the business is doing ' +
      'or what needs them today. This is the same list the command-center home shows; never invent items.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  // ── Write-PREVIEW tools (spec 007 M3). These PREPARE a write; they never record it. ──
  // There is still no commit tool: the owner confirms in the command center (or an obvious,
  // reversible, owner-grounded write is auto-confirmed by the client). After calling one,
  // tell the owner what you prepared — do NOT say it is already saved.
  {
    name: 'register_sale',
    description:
      'Prepare recording a sale. Does NOT record it by itself: it stages a proposal the owner confirms ' +
      '(or that is auto-confirmed when it is obvious and reversible). "product" is what was sold; ' +
      '"quantity" defaults to 1; "unit_amount" is the price per unit the owner stated, in whole currency ' +
      'units (e.g. 400), when they stated one. After calling, tell the owner what you prepared; never claim ' +
      'it is already saved.',
    inputSchema: {
      type: 'object',
      properties: {
        product: { type: 'string' },
        quantity: { type: 'integer', minimum: 1 },
        unit_amount: { type: 'number' },
      },
      required: ['product'],
      additionalProperties: false,
    },
  },
  {
    name: 'register_expense',
    description:
      'Prepare recording a business expense. Does NOT record it by itself. "amount" is the amount in whole ' +
      'currency units the owner stated; "description" is what it was for; "category" is optional. After ' +
      'calling, tell the owner what you prepared; never claim it is already saved.',
    inputSchema: {
      type: 'object',
      properties: {
        amount: { type: 'number' },
        description: { type: 'string' },
        category: { type: 'string' },
      },
      required: ['amount', 'description'],
      additionalProperties: false,
    },
  },
  {
    name: 'add_stock',
    description:
      'Prepare adding stock (units on hand) to a product. Does NOT record it by itself. "product" is the ' +
      'product; "quantity" is how many units to add. After calling, tell the owner what you prepared; never ' +
      'claim it is already saved.',
    inputSchema: {
      type: 'object',
      properties: {
        product: { type: 'string' },
        quantity: { type: 'integer', minimum: 1 },
      },
      required: ['product', 'quantity'],
      additionalProperties: false,
    },
  },
  // ── Confirm-only write previews (spec 007 M4, D-044): irreversible / bulk / destructive. ──
  // These ALWAYS wait for the owner to confirm (they never auto-complete). Prepare them, then
  // tell the owner what will change and that it needs their confirmation; never claim it is done.
  {
    name: 'update_product_price',
    description:
      'Prepare CHANGING a product\'s sale price. Irreversible (the old price is not kept), so it always ' +
      'needs the owner\'s confirmation. "product" is the product; "new_amount" is the new price in whole ' +
      'currency units. After calling, tell the owner the old and new price and that they must confirm.',
    inputSchema: {
      type: 'object',
      properties: { product: { type: 'string' }, new_amount: { type: 'number' } },
      required: ['product', 'new_amount'],
      additionalProperties: false,
    },
  },
  {
    name: 'register_product',
    description:
      'Prepare CREATING a new product in the catalog. Always needs the owner\'s confirmation. "name" is the ' +
      'product name; "price_amount" is its sale price in whole currency units; "cost_amount" is optional.',
    inputSchema: {
      type: 'object',
      properties: {
        name: { type: 'string' },
        price_amount: { type: 'number' },
        cost_amount: { type: 'number' },
      },
      required: ['name', 'price_amount'],
      additionalProperties: false,
    },
  },
  {
    name: 'register_products_batch',
    description:
      'Prepare CREATING several products at once. Always needs ONE confirmation for the whole set. ' +
      '"products" is a list, each with "name" and "price_amount" (and optional "cost_amount").',
    inputSchema: {
      type: 'object',
      properties: {
        products: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              price_amount: { type: 'number' },
              cost_amount: { type: 'number' },
            },
            required: ['name', 'price_amount'],
            additionalProperties: false,
          },
        },
      },
      required: ['products'],
      additionalProperties: false,
    },
  },
  {
    name: 'deactivate_product',
    description:
      'Prepare DEACTIVATING (hiding) a product so it is no longer sold. Always needs the owner\'s ' +
      'confirmation. "product" is the product to deactivate.',
    inputSchema: {
      type: 'object',
      properties: { product: { type: 'string' } },
      required: ['product'],
      additionalProperties: false,
    },
  },
  {
    name: 'cancel_last_operation',
    description:
      'Prepare CANCELLING the most recent operation (the last sale, expense, or stock entry). Takes no ' +
      'arguments. Always needs the owner\'s confirmation and shows exactly which operation would be cancelled.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
];

// Generic call to an internal read endpoint. Returns an MCP tool-result content object.
// Never throws for an operational failure: it returns an is_error content so the model
// can tell the owner something went wrong instead of the loop crashing. `label` names the
// tool in any error message; `resultKey` is the field lifted from the {ok:true,...} body.
export async function callRead(
  { opsUrl, token, phone, path, body = '{}', fetchImpl = fetch } = {},
  { label, resultKey } = {},
) {
  if (!opsUrl || !token || !phone) {
    return { content: [{ type: 'text', text: `${label} not configured (missing ops url, token, or tenant).` }], isError: true };
  }
  const url = opsUrl.replace(/\/$/, '') + path;
  // Egress allowlist (AC12): a tool may only ever reach the ops API (+ Anthropic). Fail closed.
  if (!isEgressAllowed(url, egressAllowlist({ opsUrl }))) {
    return { content: [{ type: 'text', text: `${label} blocked: egress not allowed to ${url}` }], isError: true };
  }
  let res;
  try {
    res = await fetchImpl(url, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-internal-token': token,
        'x-beans-tenant': phone,
      },
      body,
    });
  } catch (e) {
    return { content: [{ type: 'text', text: `${label} could not reach the operation API: ` + e.message }], isError: true };
  }
  let payload;
  try { payload = await res.json(); } catch { payload = null; }
  if (!res.ok || !payload || payload.ok !== true) {
    const msg = (payload && payload.error && payload.error.message) || (`${label} failed (HTTP ` + res.status + ')');
    return { content: [{ type: 'text', text: msg }], isError: true };
  }
  // Return only the named result field, under a stable top-level key, so the model gets a
  // tight JSON blob rather than the transport envelope.
  const out = resultKey ? { [resultKey]: payload[resultKey] } : payload;
  return { content: [{ type: 'text', text: JSON.stringify(out) }] };
}

export async function readStock(cfg = {}) {
  return callRead({ ...cfg, path: '/internal/ops/read_stock' }, { label: 'read_stock', resultKey: 'stock' });
}

export async function readRevenue(cfg = {}) {
  return callRead({ ...cfg, path: '/internal/ops/read_revenue' }, { label: 'read_revenue', resultKey: 'revenue' });
}

export async function readProfit(cfg = {}) {
  return callRead({ ...cfg, path: '/internal/ops/read_profit' }, { label: 'read_profit', resultKey: 'profit' });
}

export async function readSalesSummary(cfg = {}, { limit } = {}) {
  const body = JSON.stringify(Number.isInteger(limit) ? { limit } : {});
  return callRead({ ...cfg, path: '/internal/ops/read_sales_summary', body }, { label: 'read_sales_summary', resultKey: 'sales_summary' });
}

export async function readModule(cfg = {}, { module } = {}) {
  const body = JSON.stringify({ module });
  return callRead({ ...cfg, path: '/internal/ops/read_module', body }, { label: 'read_module', resultKey: 'module' });
}

export async function businessStatus(cfg = {}) {
  return callRead({ ...cfg, path: '/internal/ops/business_status' }, { label: 'business_status', resultKey: 'attention' });
}

// Call an internal write-PREVIEW endpoint. Returns the staged preview (or a clarify) to the
// model, but NEVER the op_token: the commit handle travels only to the owner's browser via the
// chat envelope metadata, so even a hijacked model holds nothing that could commit (D-040).
export async function callPreview({ opsUrl, token, phone, path, body = '{}', turnNonce, flowNonce, owner, fetchImpl = fetch } = {}, { label } = {}) {
  if (!opsUrl || !token || !phone) {
    return { content: [{ type: 'text', text: `${label} not configured (missing ops url, token, or tenant).` }], isError: true };
  }
  const url = opsUrl.replace(/\/$/, '') + path;
  if (!isEgressAllowed(url, egressAllowlist({ opsUrl }))) {
    return { content: [{ type: 'text', text: `${label} blocked: egress not allowed to ${url}` }], isError: true };
  }
  const headers = { 'content-type': 'application/json', 'x-internal-token': token, 'x-beans-tenant': phone };
  // Pin the per-turn nonce out of band so the server stamps the staged op with this turn's id,
  // and the flow nonce + owner so the internal endpoint grounds the verdict against the
  // server-authenticated operator_turns record keyed by (owner, flowNonce), NEVER these tool
  // args (spec 010 M3, T-015/T-014, D-061). All three come from the gateway-injected child env,
  // never from the model: the model cannot read or set a header.
  if (turnNonce) headers['x-beans-turn'] = turnNonce;
  if (flowNonce) headers['x-beans-flow'] = flowNonce;
  if (owner) headers['x-beans-owner'] = owner;
  let res;
  try {
    res = await fetchImpl(url, { method: 'POST', headers, body });
  } catch (e) {
    return { content: [{ type: 'text', text: `${label} could not reach the operation API: ` + e.message }], isError: true };
  }
  let payload;
  try { payload = await res.json(); } catch { payload = null; }
  if (!res.ok || !payload || payload.ok !== true) {
    const msg = (payload && payload.error && payload.error.message) || (`${label} failed (HTTP ` + res.status + ')');
    return { content: [{ type: 'text', text: msg }], isError: true };
  }
  // Strip the transport ok flag and the commit handle before handing anything to the model.
  const { ok, op_token, ...visible } = payload; // eslint-disable-line no-unused-vars
  return { content: [{ type: 'text', text: JSON.stringify(visible) }] };
}

export async function registerSale(cfg = {}, { product, quantity, unit_amount } = {}) {
  const body = JSON.stringify({ product, quantity, unit_amount });
  return callPreview({ ...cfg, path: '/internal/ops/preview/register_sale', body }, { label: 'register_sale' });
}

export async function registerExpense(cfg = {}, { amount, description, category } = {}) {
  const body = JSON.stringify({ amount, description, category });
  return callPreview({ ...cfg, path: '/internal/ops/preview/register_expense', body }, { label: 'register_expense' });
}

export async function addStock(cfg = {}, { product, quantity } = {}) {
  const body = JSON.stringify({ product, quantity });
  return callPreview({ ...cfg, path: '/internal/ops/preview/add_stock', body }, { label: 'add_stock' });
}

export async function updateProductPrice(cfg = {}, { product, new_amount } = {}) {
  const body = JSON.stringify({ product, new_amount });
  return callPreview({ ...cfg, path: '/internal/ops/preview/update_product_price', body }, { label: 'update_product_price' });
}

export async function registerProduct(cfg = {}, { name, price_amount, cost_amount } = {}) {
  const body = JSON.stringify({ name, price_amount, cost_amount });
  return callPreview({ ...cfg, path: '/internal/ops/preview/register_product', body }, { label: 'register_product' });
}

export async function registerProductsBatch(cfg = {}, { products } = {}) {
  const body = JSON.stringify({ products });
  return callPreview({ ...cfg, path: '/internal/ops/preview/register_products_batch', body }, { label: 'register_products_batch' });
}

export async function deactivateProduct(cfg = {}, { product } = {}) {
  const body = JSON.stringify({ product });
  return callPreview({ ...cfg, path: '/internal/ops/preview/deactivate_product', body }, { label: 'deactivate_product' });
}

export async function cancelLastOperation(cfg = {}) {
  return callPreview({ ...cfg, path: '/internal/ops/preview/cancel_last_operation', body: '{}' }, { label: 'cancel_last_operation' });
}

// Build a JSON-RPC dispatcher. Each `*Impl` is injectable for tests.
export function makeDispatcher({
  readStockImpl = readStock,
  readRevenueImpl = readRevenue,
  readProfitImpl = readProfit,
  readSalesSummaryImpl = readSalesSummary,
  readModuleImpl = readModule,
  businessStatusImpl = businessStatus,
  registerSaleImpl = registerSale,
  registerExpenseImpl = registerExpense,
  addStockImpl = addStock,
  updateProductPriceImpl = updateProductPrice,
  registerProductImpl = registerProduct,
  registerProductsBatchImpl = registerProductsBatch,
  deactivateProductImpl = deactivateProduct,
  cancelLastOperationImpl = cancelLastOperation,
  config = {},
} = {}) {
  return async function dispatch(msg) {
    const { id, method, params } = msg || {};
    if (method === 'initialize') {
      const pv = (params && params.protocolVersion) || '2024-11-05';
      return { jsonrpc: '2.0', id, result: { protocolVersion: pv, capabilities: { tools: {} }, serverInfo: { name: 'beans', version: '0.2.0' } } };
    }
    if (method && method.startsWith('notifications/')) return null; // notifications get no response
    if (method === 'tools/list') {
      return { jsonrpc: '2.0', id, result: { tools: TOOLS } };
    }
    if (method === 'tools/call') {
      const name = params && params.name;
      const args = (params && params.arguments) || {};
      let r;
      if (name === 'read_stock') r = await readStockImpl(config);
      else if (name === 'read_revenue') r = await readRevenueImpl(config);
      else if (name === 'read_profit') r = await readProfitImpl(config);
      else if (name === 'read_sales_summary') r = await readSalesSummaryImpl(config, { limit: args.limit });
      else if (name === 'read_module') r = await readModuleImpl(config, { module: args.module });
      else if (name === 'business_status') r = await businessStatusImpl(config);
      else if (name === 'register_sale') r = await registerSaleImpl(config, { product: args.product, quantity: args.quantity, unit_amount: args.unit_amount });
      else if (name === 'register_expense') r = await registerExpenseImpl(config, { amount: args.amount, description: args.description, category: args.category });
      else if (name === 'add_stock') r = await addStockImpl(config, { product: args.product, quantity: args.quantity });
      else if (name === 'update_product_price') r = await updateProductPriceImpl(config, { product: args.product, new_amount: args.new_amount });
      else if (name === 'register_product') r = await registerProductImpl(config, { name: args.name, price_amount: args.price_amount, cost_amount: args.cost_amount });
      else if (name === 'register_products_batch') r = await registerProductsBatchImpl(config, { products: args.products });
      else if (name === 'deactivate_product') r = await deactivateProductImpl(config, { product: args.product });
      else if (name === 'cancel_last_operation') r = await cancelLastOperationImpl(config);
      else return { jsonrpc: '2.0', id, error: { code: -32601, message: 'unknown tool ' + name } };
      return { jsonrpc: '2.0', id, result: r };
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
    // The gateway injects these per request (out of band, never a model input): the turn nonce
    // stamps a staged write; the flow nonce + owner let the internal endpoint ground the verdict
    // against operator_turns keyed by (owner, flowNonce) (spec 010 M3, T-015, D-061).
    turnNonce: process.env.BEANS_TURN_NONCE,
    flowNonce: process.env.BEANS_FLOW_NONCE,
    owner: process.env.BEANS_OWNER,
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
