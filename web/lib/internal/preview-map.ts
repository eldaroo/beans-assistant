// Pure mapping from an MCP write-preview tool call to a stageOperation input (spec 010 M3,
// T-013/T-014). The MCP tools (deploy/beans-mcp.mjs) POST their raw tool args to
// /api/internal/ops/preview/<tool>; this module turns <tool> + those args into the
// { operationType, args } the registry's stageOperation re-derives from.
//
// THE KEYSTONE, kept honest here (D-061, AC5): this mapping NEVER produces the utterance or the
// grounding corpus. Those are built at the endpoint from the server-authenticated operator_turns
// record (groundingCorpusFor(owner, flowNonce)), never from the model's tool args. A
// model-invented numeral rides only in `args` and is grounded AGAINST the operator's own words,
// so it fails grounding and cannot auto-post. Keeping this mapping a pure args -> op-args
// transform (nothing else) is what makes that property auditable: there is no code path here
// that could lift a tool arg into the grounding source.
//
// M3 wired the single reversible preview (register_sale, T-016). M4 (T-018) completes the
// reversible set (register_expense, add_stock), so the whole auto-able set round-trips through
// the box. M5 (T-022) wires the confirm-only tools (update_product_price, register_product,
// register_products_batch, deactivate_product, cancel_last_operation). An unmapped tool is a
// clean error, never a silent no-op.

export type StageInput = { operationType: string; args: Record<string, unknown> };
export type PreviewMapResult =
  | { ok: true; input: StageInput }
  // A batch tool (register_products_batch) maps to several staged ops under one turn; the
  // route stages each and the chat readback renders one confirm card per product. Each op is
  // confirm-only (REGISTER_PRODUCT is irreversible), so a batch never auto-posts.
  | { ok: true; batch: StageInput[] }
  | { ok: false; code: string; message: string };

// A single register_products_batch call may stage at most this many products. A bound on the
// fan-out (council: Tamir) so a hijacked model cannot stage thousands of inert previews in one
// tool call; 50 is far above any real one-message product drop.
export const BATCH_MAX = 50;

// Whole currency units -> cents, matching the parser's Math.round(v * 100) convention
// (lib/parse/fallback.ts). A non-finite OR negative amount yields undefined so the op stages
// price-less rather than staging a negative-price sale the parser could never produce (a write
// grounding keeps off the auto path, but should not even reach a confirm card — council: Amelia).
function toCents(whole: unknown): number | undefined {
  if (whole == null) return undefined;
  const n = Number(whole);
  if (!Number.isFinite(n) || n < 0) return undefined;
  // Guard the OUTPUT too, not only the input (council: Tamir/Winston): a finite-but-astronomical
  // amount overflows Math.round(n * 100) to Infinity, which is `!== undefined` and would stage a
  // garbage confirm card. Keep the invariant this function's doc promises — non-finite yields
  // undefined — and keep the three coercions consistent (register_sale/add_stock guard the output).
  const cents = Math.round(n * 100);
  return Number.isFinite(cents) ? cents : undefined;
}

export function mapPreviewTool(tool: string, args: Record<string, unknown>): PreviewMapResult {
  switch (tool) {
    case "register_sale": {
      const product = typeof args.product === "string" ? args.product.trim() : "";
      if (!product) return { ok: false, code: "bad_tool_args", message: "register_sale requires a product" };
      // Coerce then round, matching the parser's Math.round(nums[0].value) (fallback.ts), so a
      // stringified or float quantity resolves to the real count instead of silently defaulting
      // to 1 (council: Amelia). A non-positive or non-numeric quantity falls back to 1.
      const qn = Math.round(Number(args.quantity));
      const quantity = Number.isFinite(qn) && qn > 0 ? qn : 1;
      // The exact REGISTER_SALE shape the parser produces, so stageOperation.resolve behaves
      // identically whichever brain proposed it: one item carrying a descriptor, a quantity,
      // and (only when stated) a unit price in cents. The product id is never model-supplied;
      // stageOperation resolves it server-side.
      const item: Record<string, unknown> = { productRef: product, quantity };
      const cents = toCents(args.unit_amount);
      if (cents !== undefined) item.unitPriceCents = cents;
      return { ok: true, input: { operationType: "REGISTER_SALE", args: { items: [item] } } };
    }
    case "register_expense": {
      // The MCP register_expense tool sends { amount (whole units), description, category? }.
      // The REGISTER_EXPENSE op (registry.ts) commits { amountCents, description } and grounds
      // the amount; category is not part of the op shape, so it is dropped (an unmapped tool
      // arg never reaches the grounding source — the keystone holds). A non-finite or negative
      // amount is a clean error, never a silently-defaulted or negative-cost expense.
      const cents = toCents(args.amount);
      if (cents === undefined) return { ok: false, code: "bad_tool_args", message: "register_expense requires a non-negative amount" };
      // The description is model-authored free text that rides onto the ledger (it is not a numeral
      // or product, so it is not grounded). Bound it (council: Tamir) so a hijacked model cannot
      // write an unbounded blob into the audit/ledger; 200 chars is ample for a real expense note.
      const description = typeof args.description === "string" ? args.description.trim().slice(0, 200) : "";
      if (!description) return { ok: false, code: "bad_tool_args", message: "register_expense requires a description" };
      return { ok: true, input: { operationType: "REGISTER_EXPENSE", args: { amountCents: cents, description } } };
    }
    case "add_stock": {
      // The MCP add_stock tool sends { product, quantity }. The ADD_STOCK op resolves the
      // product server-side from the descriptor (never a model id) and grounds the quantity.
      // Quantity is coerced + rounded like register_sale; a non-positive value falls back to 1.
      const product = typeof args.product === "string" ? args.product.trim() : "";
      if (!product) return { ok: false, code: "bad_tool_args", message: "add_stock requires a product" };
      const qn = Math.round(Number(args.quantity));
      const quantity = Number.isFinite(qn) && qn > 0 ? qn : 1;
      return { ok: true, input: { operationType: "ADD_STOCK", args: { productRef: product, quantity } } };
    }
    // ── Confirm-only tools (spec 010 M5, T-022). Each maps to an irreversible registry op, so
    // computeVerdict forces auto:false (requiresHumanReview) and the owner confirms on a card.
    // The keystone holds: these mappings never produce the utterance or grounding corpus either;
    // the endpoint still builds those from operator_turns. A price/amount is a model-authored
    // numeral that rides only in args and is grounded against the operator's own words, but since
    // the op is confirm-only the grounding never gates auto-post — the human card is the gate.
    case "update_product_price": {
      const product = typeof args.product === "string" ? args.product.trim() : "";
      if (!product) return { ok: false, code: "bad_tool_args", message: "update_product_price requires a product" };
      const cents = toCents(args.new_amount);
      if (cents === undefined) return { ok: false, code: "bad_tool_args", message: "update_product_price requires a non-negative new_amount" };
      return { ok: true, input: { operationType: "UPDATE_PRICE", args: { productRef: product, unitPriceCents: cents } } };
    }
    case "register_product": {
      const r = mapRegisterProduct(args);
      return r.ok ? { ok: true, input: { operationType: "REGISTER_PRODUCT", args: r.args } } : r;
    }
    case "register_products_batch": {
      const list = Array.isArray(args.products) ? args.products : null;
      if (!list || list.length === 0) return { ok: false, code: "bad_tool_args", message: "register_products_batch requires a non-empty products list" };
      if (list.length > BATCH_MAX) return { ok: false, code: "bad_tool_args", message: `register_products_batch is limited to ${BATCH_MAX} products` };
      const batch: StageInput[] = [];
      for (const p of list) {
        const r = mapRegisterProduct((p ?? {}) as Record<string, unknown>);
        if (!r.ok) return r; // one bad product fails the whole set, nothing is staged ambiguously
        batch.push({ operationType: "REGISTER_PRODUCT", args: r.args });
      }
      return { ok: true, batch };
    }
    case "deactivate_product": {
      const product = typeof args.product === "string" ? args.product.trim() : "";
      if (!product) return { ok: false, code: "bad_tool_args", message: "deactivate_product requires a product" };
      return { ok: true, input: { operationType: "DEACTIVATE_PRODUCT", args: { productRef: product } } };
    }
    case "cancel_last_operation":
      // No args by design: the registry CANCEL_LAST op resolves the single most-recent operation
      // (sale / expense / stock) server-side and stages the matching cancel, confirm-only. The
      // model names nothing to cancel; the server picks the newest and shows the owner which one.
      return { ok: true, input: { operationType: "CANCEL_LAST", args: {} } };
    default:
      // Any tool not mapped above is a clean error, never a silent no-op.
      return { ok: false, code: "unsupported_tool", message: `write-preview tool ${tool} is not wired` };
  }
}

// Map the register_product arg shape ({ name, price_amount, cost_amount? }) to REGISTER_PRODUCT
// args. Shared by the single tool and the batch tool. A stated price is carried through (the
// name-only auto-mint used by the compound heal leaves price pending; an explicit register does
// not), and a stated cost overrides the mint's 0 placeholder. A non-finite/negative amount is a
// clean error, never a silently-defaulted or negative value.
function mapRegisterProduct(
  args: Record<string, unknown>,
): { ok: true; args: Record<string, unknown> } | { ok: false; code: string; message: string } {
  const name = typeof args.name === "string" ? args.name.trim().slice(0, 120) : "";
  if (!name) return { ok: false, code: "bad_tool_args", message: "register_product requires a name" };
  const price = toCents(args.price_amount);
  if (price === undefined) return { ok: false, code: "bad_tool_args", message: "register_product requires a non-negative price_amount" };
  const out: Record<string, unknown> = { name, unitPriceCents: price };
  const cost = toCents(args.cost_amount);
  if (cost !== undefined) out.unitCostCents = cost;
  return { ok: true, args: out };
}
