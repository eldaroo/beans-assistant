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
// M3 wires the single reversible preview (register_sale, T-016). M4 (T-018) adds the rest of the
// reversible set (register_expense, add_stock); M5 (T-022) wires the confirm-only tools
// (update_product_price, register_product, register_products_batch, deactivate_product,
// cancel_last_operation). An unmapped tool is a clean error, never a silent no-op.

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
  return Math.round(n * 100);
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
    default:
      // register_expense / add_stock land in M4 (T-018); the confirm-only tools in M5 (T-022).
      return { ok: false, code: "unsupported_tool", message: `write-preview tool ${tool} is not wired yet` };
  }
}
