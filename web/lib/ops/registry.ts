// The operation registry ties the parser's proposal to the app's own verdict and
// commit. The parser (M6) produces a proposal {operationType, args, utterance};
// the app RE-DERIVES the product resolution, the grounded amounts, and the verdict
// here, never trusting a model-supplied flag. Only /confirm (a non-model route)
// runs commit. (spec 008 AC5/AC6.)

import { resolveActiveProduct, getProduct } from "@/lib/domains/products";
import { registerSale, cancelSale } from "@/lib/domains/sales";
import { registerExpense, cancelExpense } from "@/lib/domains/expenses";
import { addStock, cancelStockMovement } from "@/lib/domains/stock";
import { createProduct, updateProduct, deactivateProduct } from "@/lib/domains/products";

export interface ResolveResult {
  stagedArgs: Record<string, unknown>;
  productName: string | null;
  candidateCount: number;
  groundedAmounts: Array<number | string>;
}

export interface OpDef {
  irreversible: boolean;
  // Re-derive product resolution + the load-bearing amounts that must trace to
  // the operator's utterance. Never trusts model-supplied resolution.
  resolve(args: Record<string, unknown>): Promise<ResolveResult>;
  commit(args: Record<string, unknown>): Promise<unknown>;
  undo?(commitResult: Record<string, unknown>): Promise<unknown>;
}

async function resolveOneProduct(args: {
  productId?: number;
  productRef?: string;
}): Promise<{ id: number | null; name: string | null; candidateCount: number }> {
  if (args.productId != null) {
    try {
      const p = await getProduct(args.productId);
      return { id: p.id, name: p.name, candidateCount: 1 };
    } catch {
      return { id: null, name: null, candidateCount: 0 };
    }
  }
  const r = await resolveActiveProduct(args.productRef ?? "");
  return { id: r.product?.id ?? null, name: r.product?.name ?? null, candidateCount: r.candidateCount };
}

type SaleArgs = {
  items: Array<{ productId?: number; productRef?: string; quantity: number; unitPriceCents?: number }>;
  customerName?: string | null;
};

export const OPS: Record<string, OpDef> = {
  // ----------------------------------------------------- reversible (auto-able)
  REGISTER_SALE: {
    irreversible: false,
    async resolve(rawArgs) {
      const args = rawArgs as SaleArgs;
      const items = args.items ?? [];
      // Auto-post is only for a single-product turn; a multi-item sale always
      // routes to a confirm card (candidateCount 0 keeps it off the auto path).
      if (items.length !== 1) {
        return { stagedArgs: rawArgs, productName: null, candidateCount: items.length ? 2 : 0, groundedAmounts: [] };
      }
      const it = items[0];
      const r = await resolveOneProduct(it);
      const grounded: Array<number | string> = [];
      if (it.quantity > 1) grounded.push(it.quantity);
      if (it.unitPriceCents != null) grounded.push(it.unitPriceCents / 100);
      const stagedArgs = { ...args, items: [{ ...it, productId: r.id ?? it.productId }] };
      return { stagedArgs, productName: r.name, candidateCount: r.candidateCount, groundedAmounts: grounded };
    },
    commit: (args) => registerSale(args as SaleArgs),
    undo: (res) => cancelSale(res.sale_id as number),
  },

  REGISTER_EXPENSE: {
    irreversible: false,
    async resolve(rawArgs) {
      const args = rawArgs as { amountCents: number };
      return {
        stagedArgs: rawArgs,
        productName: null, // a pure expense carries no product to ground
        candidateCount: 1, // determinism does not apply; keep off the "no match" path
        groundedAmounts: [args.amountCents / 100],
      };
    },
    commit: (args) => registerExpense(args as { amountCents: number; description: string }),
    undo: (res) => cancelExpense(res.expense_id as number),
  },

  ADD_STOCK: {
    irreversible: false,
    async resolve(rawArgs) {
      const args = rawArgs as { productId?: number; productRef?: string; quantity: number };
      const r = await resolveOneProduct(args);
      return {
        stagedArgs: { ...args, productId: r.id ?? args.productId },
        productName: r.name,
        candidateCount: r.candidateCount,
        groundedAmounts: [args.quantity],
      };
    },
    commit: (args) => addStock(args as { productId: number; quantity: number }),
    undo: (res) => cancelStockMovement(res.movement_id as number),
  },

  // ------------------------------------------------------------- confirm-only
  REGISTER_PRODUCT: {
    irreversible: true,
    async resolve(rawArgs) {
      return { stagedArgs: rawArgs, productName: null, candidateCount: 1, groundedAmounts: [] };
    },
    commit: (args) => createProduct(args as { sku: string; name: string; unitCostCents: number }),
  },

  UPDATE_PRICE: {
    irreversible: true,
    async resolve(rawArgs) {
      const args = rawArgs as { productId: number };
      const p = await resolveOneProduct(args);
      return { stagedArgs: rawArgs, productName: p.name, candidateCount: p.candidateCount, groundedAmounts: [] };
    },
    commit: (args) => {
      const a = args as { productId: number; unitPriceCents: number };
      return updateProduct(a.productId, { unitPriceCents: a.unitPriceCents });
    },
  },

  DEACTIVATE_PRODUCT: {
    irreversible: true,
    async resolve(rawArgs) {
      const args = rawArgs as { productId: number };
      const p = await resolveOneProduct(args);
      return { stagedArgs: rawArgs, productName: p.name, candidateCount: p.candidateCount, groundedAmounts: [] };
    },
    commit: (args) => deactivateProduct((args as { productId: number }).productId),
  },

  CANCEL_SALE: {
    irreversible: true,
    async resolve(rawArgs) {
      return { stagedArgs: rawArgs, productName: null, candidateCount: 1, groundedAmounts: [] };
    },
    commit: (args) => cancelSale((args as { saleId: number }).saleId),
  },

  CANCEL_EXPENSE: {
    irreversible: true,
    async resolve(rawArgs) {
      return { stagedArgs: rawArgs, productName: null, candidateCount: 1, groundedAmounts: [] };
    },
    commit: (args) => cancelExpense((args as { expenseId: number }).expenseId),
  },

  CANCEL_STOCK: {
    irreversible: true,
    async resolve(rawArgs) {
      return { stagedArgs: rawArgs, productName: null, candidateCount: 1, groundedAmounts: [] };
    },
    commit: (args) => cancelStockMovement((args as { movementId: number }).movementId),
  },
};

// The destructive ops (tighter rate cap name space in lib/audit).
export const DESTRUCTIVE_OP_TYPES = new Set(["DEACTIVATE_PRODUCT", "CANCEL_SALE", "CANCEL_EXPENSE", "CANCEL_STOCK"]);

export function getOp(operationType: string): OpDef | null {
  return OPS[operationType?.toUpperCase?.()] ?? null;
}
