// The operation registry ties the parser's proposal to the app's own verdict and
// commit. The parser (M6) produces a proposal {operationType, args, utterance};
// the app RE-DERIVES the product resolution, the grounded amounts, and the verdict
// here, never trusting a model-supplied flag. Only /confirm (a non-model route)
// runs commit. (spec 008 AC5/AC6.)

import { resolveActiveProduct, getProduct, type ProductRow } from "@/lib/domains/products";
import { registerSale, cancelSale, listSales } from "@/lib/domains/sales";
import { registerExpense, cancelExpense, listExpenses } from "@/lib/domains/expenses";
import { addStock, cancelStockMovement, recentStockMovements } from "@/lib/domains/stock";
import { createProduct, updateProduct, deactivateProduct } from "@/lib/domains/products";
import { recordProduction, normalizeWeek } from "@/lib/domains/production";
import { createSupplier, recordCheckin } from "@/lib/domains/suppliers";
import { mintMinimalProductArgs } from "@/lib/ops/mint";
import {
  resolveSale,
  resolveExpense,
  resolveStockMovement,
  resolveSupplier,
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
          // Honor an explicitly-stated price/cost (spec 010 M5, the register_product tool path):
          // the name-only auto-mint used by the compound heal leaves price pending (null), but an
          // explicit "register product X at $Y" keeps Y. A stated cost overrides the 0 placeholder.
          const withStated = {
            ...minted,
            ...(args.unitPriceCents != null ? { unitPriceCents: args.unitPriceCents } : {}),
            ...(args.unitCostCents != null ? { unitCostCents: args.unitCostCents } : {}),
          };
          return { stagedArgs: withStated as unknown as Record<string, unknown>, productName: withStated.name, candidateCount: 1, groundedAmounts: [] };
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

  // Cancel the single most-recent operation across sales, expenses, and stock entries
  // (spec 010 M5, T-022; the cancel_last_operation tool). The model names nothing: resolve
  // reads the newest row of each kind, picks the newest overall by timestamp, and stages the
  // matching cancel. Confirm-only (irreversible + requiresHumanReview) and destructive-capped.
  CANCEL_LAST: {
    irreversible: true,
    requiresHumanReview: true,
    // refNoun so an empty ledger (candidateCount 0) yields the clean "no encontre una operacion"
    // reference_not_found message from stage, not the misleading product-not-found copy. CANCEL_LAST
    // never disambiguates (no refIdField): it always picks the single newest op server-side.
    refNoun: "operacion",
    async resolve() {
      const [sales, expenses, stock] = await Promise.all([
        listSales({ limit: 1 }),
        listExpenses({ limit: 1 }),
        recentStockMovements(1),
      ]);
      const cands: Array<LastOpCandidate | null> = [
        sales[0] ? { kind: "sale", id: sales[0].id, label: `la venta #${sales[0].id}`, whenMs: toMs(sales[0].createdAt) } : null,
        expenses[0] ? { kind: "expense", id: expenses[0].id, label: `el gasto #${expenses[0].id}`, whenMs: toMs(expenses[0].createdAt) } : null,
        stock[0] ? { kind: "stock", id: stock[0].id, label: `el movimiento de stock #${stock[0].id}`, whenMs: toMs(stock[0].occurredAt) } : null,
      ];
      const newest = pickNewestOperation(cands);
      if (!newest) {
        // Nothing on the ledger to cancel: candidateCount 0 yields a clean message from stage.
        return { stagedArgs: {}, productName: null, candidateCount: 0, groundedAmounts: [] };
      }
      const preview =
        newest.kind === "sale"
          ? `Cancelar ${newest.label}. Si estaba pagada, se revierte el stock vendido al inventario.`
          : newest.kind === "expense"
            ? `Cancelar ${newest.label}. Se registra una cancelacion que lo neutraliza en el total.`
            : `Revertir ${newest.label}. Se descuenta esa entrada del inventario.`;
      return { stagedArgs: { kind: newest.kind, id: newest.id }, productName: null, candidateCount: 1, groundedAmounts: [], preview };
    },
    commit: (args) => {
      const a = args as { kind: string; id: number };
      if (a.kind === "sale") return cancelSale(a.id);
      if (a.kind === "expense") return cancelExpense(a.id);
      return cancelStockMovement(a.id);
    },
  },

  // ------------------------------------- orphan operational writes (spec 009 M6 / AC12)
  // Production record, supplier create, supplier check-in, product non-price edit — each
  // reachable from chat and each confirm-only (irreversible: true keeps them off the
  // auto-post path, so they always show a card the owner confirms). None was reachable
  // from the assistant before; they are the "connect the rest of the business" cohort.

  // Record a week's production. The optional product resolves server-side; the week
  // defaults to the current ISO week when the owner does not name one.
  RECORD_PRODUCTION: {
    irreversible: true,
    async resolve(rawArgs) {
      const args = rawArgs as { productRef?: string; country?: string; periodWeek?: string; unitsProduced?: number };
      const week = args.periodWeek ? normalizeWeek(args.periodWeek) : currentIsoWeek();
      const country = (args.country ?? "").trim();
      // Coerce + clamp a possibly-garbage model value: reject NaN, floor negatives to 0.
      const units = Math.max(0, Math.round(Number(args.unitsProduced) || 0));
      let productId: number | null = null;
      let productName: string | null = null;
      if (args.productRef) {
        const r = await resolveActiveProduct(args.productRef);
        if (r.candidateCount === 1 && r.product) {
          productId = r.product.id;
          productName = r.product.name;
        }
      }
      const where = country ? ` en ${country}` : "";
      // Honest preview (council: Amelia): if the owner named a product that did not resolve
      // to exactly one, say so instead of silently dropping it — the record still posts,
      // unassociated, and the card shows that.
      const of = productName
        ? ` de ${productName}`
        : args.productRef
          ? ` (sin asociar: no identifique "${args.productRef}")`
          : "";
      return {
        stagedArgs: { productId, country: country || null, periodWeek: week, unitsProduced: units },
        productName,
        candidateCount: 1,
        groundedAmounts: [],
        preview: `Registrar produccion${of}: ${units} unidades${where}, semana ${week}.`,
      };
    },
    commit: (args) => {
      const a = args as { productId: number | null; country: string | null; periodWeek: string; unitsProduced: number };
      return recordProduction({ productId: a.productId, country: a.country ?? "", periodWeek: a.periodWeek, unitsProduced: a.unitsProduced });
    },
  },

  // Create a supplier from a name (optional country / contact).
  CREATE_SUPPLIER: {
    irreversible: true,
    resolve: (rawArgs) => {
      const args = rawArgs as { name?: string; country?: string; contact?: string };
      const name = (args.name ?? "").trim();
      const where = args.country ? ` (${args.country})` : "";
      return Promise.resolve({
        stagedArgs: { name, country: args.country ?? null, contact: args.contact ?? null },
        productName: null,
        candidateCount: name ? 1 : 0,
        groundedAmounts: [],
        preview: `Crear proveedor ${name}${where}.`,
      });
    },
    commit: (args) => createSupplier(args as { name: string; country?: string | null; contact?: string | null }),
  },

  // Record a check-in (reply) with a supplier the owner names, resetting the overdue
  // cadence. The supplier is resolved server-side to an id; the model never supplies it.
  RECORD_CHECKIN: {
    irreversible: true,
    refIdField: "supplierId",
    refNoun: "proveedor",
    resolve: (rawArgs) => {
      const args = rawArgs as { supplierId?: number; supplierRef?: string };
      if (args.supplierId != null) {
        return Promise.resolve({ stagedArgs: { supplierId: args.supplierId }, productName: null, candidateCount: 1, groundedAmounts: [], preview: `Registrar contacto con el proveedor #${args.supplierId}.` });
      }
      return resolveSupplier(args.supplierRef ?? "").then((r) => fromRef(r, "supplierId", (c) => `Registrar contacto con ${c.label}. Se reinicia la cadencia de seguimiento.`));
    },
    commit: (args) => recordCheckin((args as { supplierId: number }).supplierId),
  },

  // Edit a product's non-price fields (name, sku, unit cost). Price changes go through
  // UPDATE_PRICE; this is the rename / re-sku / cost-correction path, confirm-only.
  EDIT_PRODUCT: {
    irreversible: true,
    requiresHumanReview: true,
    refIdField: "productId",
    refNoun: "producto",
    async resolve(rawArgs) {
      const args = rawArgs as { productId?: number; productRef?: string; name?: string; sku?: string; unitCostCents?: number };
      const edits: Record<string, unknown> = {};
      if (args.name != null) edits.name = String(args.name).trim();
      if (args.sku != null) edits.sku = String(args.sku).trim();
      // Coerce + clamp the cost: reject NaN, floor negatives to 0 (the model is an
      // uncontrolled source; the human card is the last guard but the value is sane here).
      if (args.unitCostCents != null) edits.unitCostCents = Math.max(0, Math.round(Number(args.unitCostCents) || 0));
      const changeText = describeProductEdits(edits);
      // Resolve the product ONCE (council: Amelia — no double DB round-trip). By id when
      // given; else by descriptor, where more-than-one drives the disambiguation picker.
      let p: { id: number; name: string } | null = null;
      if (args.productId != null) {
        const row = await safeGetProduct(args.productId);
        if (row) p = { id: row.id, name: row.name };
      } else {
        const res = await resolveActiveProduct(args.productRef ?? "");
        if (res.candidateCount > 1) {
          // More-than-one match -> disambiguation (AC5): surface candidates, stage nothing.
          return { stagedArgs: { ...edits }, productName: null, candidateCount: res.candidateCount, groundedAmounts: [], candidates: res.candidates.map(productCandidate) };
        }
        if (res.candidateCount === 1 && res.product) p = { id: res.product.id, name: res.product.name };
      }
      if (!p) return { stagedArgs: { ...edits }, productName: null, candidateCount: 0, groundedAmounts: [] };
      return {
        stagedArgs: { productId: p.id, ...edits },
        productName: p.name,
        candidateCount: 1,
        groundedAmounts: [],
        preview: `Editar ${p.name}: ${changeText}.`,
      };
    },
    commit: (args) => {
      const a = args as { productId: number; name?: string; sku?: string; unitCostCents?: number };
      const updates: Record<string, unknown> = {};
      if (a.name !== undefined) updates.name = a.name;
      if (a.sku !== undefined) updates.sku = a.sku;
      if (a.unitCostCents !== undefined) updates.unitCostCents = a.unitCostCents;
      return updateProduct(a.productId, updates);
    },
  },
};

// Human-readable summary of a product edit for the confirm card.
function describeProductEdits(edits: Record<string, unknown>): string {
  const parts: string[] = [];
  if (typeof edits.name === "string") parts.push(`nombre a "${edits.name}"`);
  if (typeof edits.sku === "string") parts.push(`sku a ${edits.sku}`);
  if (edits.unitCostCents != null) parts.push(`costo a ${money(Number(edits.unitCostCents))}`);
  return parts.length ? parts.join(", ") : "sin cambios";
}

// Current ISO-8601 week as YYYY-Www (Monday-based), for a production record with no
// explicit week. Matches normalizeWeek's output shape.
function currentIsoWeek(d: Date = new Date()): string {
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const day = t.getUTCDay() || 7; // Mon..Sun -> 1..7
  t.setUTCDate(t.getUTCDate() + 4 - day); // nearest Thursday
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((t.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${t.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

// A most-recent-operation candidate, for CANCEL_LAST's cross-type pick (spec 010 M5). Comparison
// is on `whenMs` (epoch millis), NOT a string: the three kinds hydrate their timestamps in
// DIFFERENT shapes — sale/expense `createdAt` are Date objects (drizzle timestamp, no mode) while
// stock `occurredAt` is a raw pg string from a `sql` execute — so a lexicographic string compare
// mixes "Mon Oct 26 2026 …" (letter-leading) with "2026-10-26 …" (digit-leading) and picks the
// wrong row routinely (council: Amelia/Winston HIGH). An epoch number is format-agnostic.
export type LastOpCandidate = { kind: "sale" | "expense" | "stock"; id: number; label: string; whenMs: number };

// Epoch millis from a Date OR a timestamp string (ISO or the pg "YYYY-MM-DD HH:MM:SS+00" form).
// NaN when unparseable, so pickNewestOperation drops it rather than mis-ordering it as 0.
export function toMs(v: unknown): number {
  if (v == null) return NaN;
  if (v instanceof Date) return v.getTime();
  const s = String(v);
  const t = Date.parse(s);
  if (!Number.isNaN(t)) return t;
  return Date.parse(s.replace(" ", "T")); // pg space-separated -> ISO-ish
}

// Pick the newest operation across kinds by epoch millis (pure; testable without a DB). Candidates
// with an unparseable/missing timestamp are dropped. Ties resolve to the first of equal millis.
export function pickNewestOperation(cands: Array<LastOpCandidate | null>): LastOpCandidate | null {
  const live = cands.filter((c): c is LastOpCandidate => !!c && Number.isFinite(c.whenMs));
  if (!live.length) return null;
  return live.reduce((a, b) => (b.whenMs > a.whenMs ? b : a));
}

// The destructive ops (tighter rate cap name space in lib/audit). CANCEL_LAST is destructive:
// it reverts whichever operation it resolves, so it shares the tighter per-window cap.
export const DESTRUCTIVE_OP_TYPES = new Set(["DEACTIVATE_PRODUCT", "CANCEL_SALE", "CANCEL_EXPENSE", "CANCEL_STOCK", "CANCEL_LAST"]);

export function getOp(operationType: string): OpDef | null {
  return OPS[operationType?.toUpperCase?.()] ?? null;
}
