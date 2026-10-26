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
  | { ok: false; code: string; message: string };

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
    default:
      // The confirm-only tools (update_product_price, register_product, register_products_batch,
      // deactivate_product, cancel_last_operation) land in M5 (T-022).
      return { ok: false, code: "unsupported_tool", message: `write-preview tool ${tool} is not wired yet` };
  }
}
