// The operation registry ties the parser's proposal to the app's own verdict and
// commit. The parser (M6) produces a proposal {operationType, args, utterance};
// the app RE-DERIVES the product resolution, the grounded amounts, and the verdict
// here, never trusting a model-supplied flag. Only /confirm (a non-model route)
// runs commit. (spec 008 AC5/AC6.)

import { resolveActiveProduct, getProduct, type ProductRow } from "@/lib/domains/products";
import { registerSale, cancelSale } from "@/lib/domains/sales";
import { registerExpense, cancelExpense } from "@/lib/domains/expenses";
import { addStock, cancelStockMovement } from "@/lib/domains/stock";
import { createProduct, updateProduct, deactivateProduct } from "@/lib/domains/products";
import { mintMinimalProductArgs } from "@/lib/ops/mint";
import {
  resolveSale,
  resolveExpense,
  resolveStockMovement,
  type RefCandidate,
  type RefResolution,
} from "@/lib/ops/resolve-ref";

export interface ResolveResult {
  stagedArgs: Record<string, unknown>;
  productName: string | null;
  candidateCount: number;
  groundedAmounts: Array<number | string>;
  // The full-consequence line the confirm card shows before a destructive/edit op posts
  // (spec 009 M3 / AC6). Null for the write ops whose preview the client summarizes.
  preview?: string;
  // The disambiguation options when a descriptor resolved to more than one row
  // (spec 009 M2 / AC5). Stage emits these as a picker instead of staging.
  candidates?: RefCandidate[];
}

export interface OpDef {
  irreversible: boolean;
  // A PERMANENT, registry-level confirm-only stamp (spec 009 M3 / AC7 / s-15). Independent
  // of the dynamic verdict: destructive and cost-model ops carry it so no future grounding
  // change can ever promote them onto the auto-post path. computeVerdict honors it first.
  requiresHumanReview?: boolean;
  // The id field a disambiguation re-stage sets (spec 009 M2 / AC5). Present only on the
  // reference-resolving ops; its presence also tells stage this op can disambiguate.
  refIdField?: string;
  // The Spanish noun for a clean not-found message ("venta", "gasto", "entrada", "producto").
  refNoun?: string;
  // Re-derive product/reference resolution + the load-bearing amounts that must trace to
  // the operator's utterance. Never trusts model-supplied resolution.
  resolve(args: Record<string, unknown>): Promise<ResolveResult>;
  commit(args: Record<string, unknown>): Promise<unknown>;
  undo?(commitResult: Record<string, unknown>): Promise<unknown>;
}

// Shape a reference resolution into a ResolveResult. On a single match the id is staged
// under `idField` (server-resolved, never model-supplied) with the consequence preview; on
// 0 or more-than-1 the candidates ride through so stage emits a not-found or a picker.
function fromRef(
  r: RefResolution,
  idField: string,
  consequence: (c: RefCandidate) => string,
): ResolveResult {
  if (r.candidateCount === 1 && r.id != null) {
    const c = r.candidates[0];
    return {
      stagedArgs: { [idField]: r.id },
      productName: c.label,
      candidateCount: 1,
      groundedAmounts: [],
      preview: consequence(c),
      candidates: r.candidates,
    };
  }
  return { stagedArgs: {}, productName: null, candidateCount: r.candidateCount, groundedAmounts: [], candidates: r.candidates };
}

function money(cents: number | null | undefined): string {
  if (cents == null) return "s/d";
  return `$ ${(Number(cents) / 100).toLocaleString("es-AR", { maximumFractionDigits: 2 })}`;
}
function productCandidate(p: ProductRow): RefCandidate {
  return { id: p.id, label: p.name, detail: p.unitPriceCents != null ? `precio ${money(p.unitPriceCents)}` : "sin precio" };
}
// getProduct throws on a missing id; a direct productId only reaches the edit ops on a
// server re-stage (the chat route strips model ids), but guard it so a stale id degrades
// to a clean not-found rather than a 500.
async function safeGetProduct(id: number): Promise<ProductRow | null> {
  try {
    return await getProduct(id);
  } catch {
    return null;
  }
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
      const args = rawArgs as {
        sku?: string;
        name?: string;
        productRef?: string;
        unitCostCents?: number;
        unitPriceCents?: number | null;
      };
      // Name-only mint (spec 009 AC2): with no sku supplied, derive a minimal product
      // from the name alone (derived sku, unit cost 0, price pending). This is what lets
      // "me entraron 50 pulseras rojas" create "pulseras rojas" in one step.
      if (!args.sku) {
        const name = (args.name ?? args.productRef ?? "").trim();
        if (name) {
          const minted = mintMinimalProductArgs(name);
          return { stagedArgs: minted as unknown as Record<string, unknown>, productName: minted.name, candidateCount: 1, groundedAmounts: [] };
        }
      }
      return { stagedArgs: rawArgs, productName: args.name ?? null, candidateCount: 1, groundedAmounts: [] };
    },
    commit: (args) => createProduct(args as { sku: string; name: string; unitCostCents: number }),
  },

  // Edit a price: resolve the product by descriptor (server-side), preview the before/after
  // so the owner sees the full consequence before confirming (AC6). The new price is a
  // grounded value from the utterance; the product id is never model-supplied (AC4).
  UPDATE_PRICE: {
    irreversible: true,
    requiresHumanReview: true,
    refIdField: "productId",
    refNoun: "producto",
    async resolve(rawArgs) {
      const args = rawArgs as { productId?: number; productRef?: string; unitPriceCents?: number };
      const newPrice = money(args.unitPriceCents ?? null);
      if (args.productId != null) {
        const p = await safeGetProduct(args.productId);
        if (!p) return { stagedArgs: { unitPriceCents: args.unitPriceCents }, productName: null, candidateCount: 0, groundedAmounts: [] };
        return { stagedArgs: { productId: p.id, unitPriceCents: args.unitPriceCents }, productName: p.name, candidateCount: 1, groundedAmounts: args.unitPriceCents != null ? [args.unitPriceCents / 100] : [], preview: `Cambiar el precio de ${p.name} de ${money(p.unitPriceCents)} a ${newPrice}.` };
      }
      const res = await resolveActiveProduct(args.productRef ?? "");
      if (res.candidateCount === 1 && res.product) {
        const p = res.product;
        return { stagedArgs: { productId: p.id, unitPriceCents: args.unitPriceCents }, productName: p.name, candidateCount: 1, groundedAmounts: args.unitPriceCents != null ? [args.unitPriceCents / 100] : [], preview: `Cambiar el precio de ${p.name} de ${money(p.unitPriceCents)} a ${newPrice}.`, candidates: res.candidates.map(productCandidate) };
      }
      return { stagedArgs: { unitPriceCents: args.unitPriceCents }, productName: null, candidateCount: res.candidateCount, groundedAmounts: [], candidates: res.candidates.map(productCandidate) };
    },
    commit: (args) => {
      const a = args as { productId: number; unitPriceCents: number };
      return updateProduct(a.productId, { unitPriceCents: a.unitPriceCents });
    },
  },

  DEACTIVATE_PRODUCT: {
    irreversible: true,
    requiresHumanReview: true,
    refIdField: "productId",
    refNoun: "producto",
    async resolve(rawArgs) {
      const args = rawArgs as { productId?: number; productRef?: string };
      if (args.productId != null) {
        const p = await safeGetProduct(args.productId);
        if (!p) return { stagedArgs: {}, productName: null, candidateCount: 0, groundedAmounts: [] };
        return { stagedArgs: { productId: p.id }, productName: p.name, candidateCount: 1, groundedAmounts: [], preview: `Desactivar ${p.name}. Deja de aparecer en el catalogo y no se podra vender.` };
      }
      const res = await resolveActiveProduct(args.productRef ?? "");
      if (res.candidateCount === 1 && res.product) {
        const p = res.product;
        return { stagedArgs: { productId: p.id }, productName: p.name, candidateCount: 1, groundedAmounts: [], preview: `Desactivar ${p.name}. Deja de aparecer en el catalogo y no se podra vender.`, candidates: res.candidates.map(productCandidate) };
      }
      return { stagedArgs: {}, productName: null, candidateCount: res.candidateCount, groundedAmounts: [], candidates: res.candidates.map(productCandidate) };
    },
    commit: (args) => deactivateProduct((args as { productId: number }).productId),
  },

  CANCEL_SALE: {
    irreversible: true,
    requiresHumanReview: true,
    refIdField: "saleId",
    refNoun: "venta",
    resolve: (rawArgs) => {
      const args = rawArgs as { saleId?: number; saleRef?: string };
      if (args.saleId != null) {
        return Promise.resolve({ stagedArgs: { saleId: args.saleId }, productName: null, candidateCount: 1, groundedAmounts: [], preview: `Cancelar la venta #${args.saleId}. Si estaba pagada, se revierte el stock vendido al inventario.` });
      }
      return resolveSale(args.saleRef ?? "").then((r) => fromRef(r, "saleId", (c) => `Cancelar ${c.label}. Si estaba pagada, se revierte el stock vendido al inventario.`));
    },
    commit: (args) => cancelSale((args as { saleId: number }).saleId),
  },

  CANCEL_EXPENSE: {
    irreversible: true,
    requiresHumanReview: true,
    refIdField: "expenseId",
    refNoun: "gasto",
    resolve: (rawArgs) => {
      const args = rawArgs as { expenseId?: number; expenseRef?: string };
      if (args.expenseId != null) {
        return Promise.resolve({ stagedArgs: { expenseId: args.expenseId }, productName: null, candidateCount: 1, groundedAmounts: [], preview: `Cancelar el gasto #${args.expenseId}. Se registra una cancelacion que lo neutraliza en el total.` });
      }
      return resolveExpense(args.expenseRef ?? "").then((r) => fromRef(r, "expenseId", (c) => `Cancelar ${c.label}. Se registra una cancelacion que lo neutraliza en el total.`));
    },
    commit: (args) => cancelExpense((args as { expenseId: number }).expenseId),
  },

  CANCEL_STOCK: {
    irreversible: true,
    requiresHumanReview: true,
    refIdField: "movementId",
    refNoun: "entrada",
    resolve: (rawArgs) => {
      const args = rawArgs as { movementId?: number; movementRef?: string };
      if (args.movementId != null) {
        return Promise.resolve({ stagedArgs: { movementId: args.movementId }, productName: null, candidateCount: 1, groundedAmounts: [], preview: `Revertir el movimiento de stock #${args.movementId}. Se descuenta esa entrada del inventario.` });
      }
      return resolveStockMovement(args.movementRef ?? "").then((r) => fromRef(r, "movementId", (c) => `Revertir ${c.label}. Se descuenta esa entrada del inventario.`));
    },
    commit: (args) => cancelStockMovement((args as { movementId: number }).movementId),
  },
};

// The destructive ops (tighter rate cap name space in lib/audit).
export const DESTRUCTIVE_OP_TYPES = new Set(["DEACTIVATE_PRODUCT", "CANCEL_SALE", "CANCEL_EXPENSE", "CANCEL_STOCK"]);

export function getOp(operationType: string): OpDef | null {
  return OPS[operationType?.toUpperCase?.()] ?? null;
}
