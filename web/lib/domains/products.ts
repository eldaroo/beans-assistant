// Products domain. Ported from backend/services/products_service.py +
// backend/services/ops_resolver.py. The phone-scoped in-process cache is dropped
// (serverless); correctness rules (duplicate-SKU conflict, active-only resolution)
// are preserved.

import { and, asc, eq, ilike, sql } from "drizzle-orm";
import { db } from "@/lib/db";
import { products } from "@/db/schema";
import { centsToUsd } from "@/lib/money";

export class ProductNotFoundError extends Error {}
export class ProductConflictError extends Error {}

export type ProductRow = typeof products.$inferSelect;

export interface ProductView extends ProductRow {
  unitCostUsd: number | null;
  unitPriceUsd: number | null;
}

function toView(row: ProductRow): ProductView {
  return {
    ...row,
    unitCostUsd: centsToUsd(row.unitCostCents),
    unitPriceUsd: centsToUsd(row.unitPriceCents),
  };
}

function isDuplicateSku(msg: string): boolean {
  const l = msg.toLowerCase();
  return l.includes("duplicate key") || l.includes("unique constraint");
}

export async function listProducts(opts: {
  includeInactive?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<ProductView[]> {
  const { includeInactive = false, limit = 100, offset = 0 } = opts;
  const rows = await db
    .select()
    .from(products)
    .where(includeInactive ? undefined : eq(products.isActive, true))
    .orderBy(asc(products.name))
    .limit(limit)
    .offset(offset);
  return rows.map(toView);
}

export async function getProduct(productId: number): Promise<ProductView> {
  const rows = await db.select().from(products).where(eq(products.id, productId)).limit(1);
  if (!rows.length) throw new ProductNotFoundError(`Product ${productId} not found`);
  return toView(rows[0]);
}

export async function createProduct(payload: {
  sku: string;
  name: string;
  description?: string | null;
  unitCostCents: number;
  unitPriceCents?: number | null;
}): Promise<ProductView> {
  try {
    const [row] = await db
      .insert(products)
      .values({
        sku: payload.sku,
        name: payload.name,
        description: payload.description ?? null,
        unitCostCents: payload.unitCostCents,
        unitPriceCents: payload.unitPriceCents ?? null,
      })
      .returning();
    return toView(row);
  } catch (err) {
    if (isDuplicateSku(String((err as Error)?.message ?? err))) {
      throw new ProductConflictError(`Product with SKU '${payload.sku}' already exists`);
    }
    throw err;
  }
}

export async function updateProduct(
  productId: number,
  updates: Partial<Pick<ProductRow, "sku" | "name" | "description" | "unitCostCents" | "unitPriceCents">>,
): Promise<ProductView> {
  const clean = Object.fromEntries(
    Object.entries(updates).filter(([, v]) => v !== undefined),
  );
  if (Object.keys(clean).length === 0) return getProduct(productId);
  try {
    const rows = await db
      .update(products)
      .set(clean)
      .where(eq(products.id, productId))
      .returning();
    if (!rows.length) throw new ProductNotFoundError(`Product ${productId} not found`);
    return toView(rows[0]);
  } catch (err) {
    if (err instanceof ProductNotFoundError) throw err;
    if (isDuplicateSku(String((err as Error)?.message ?? err))) {
      throw new ProductConflictError(`SKU '${updates.sku}' already exists`);
    }
    throw err;
  }
}

export async function deactivateProduct(productId: number): Promise<{ status: string; product_id: number }> {
  const rows = await db
    .update(products)
    .set({ isActive: false })
    .where(and(eq(products.id, productId), eq(products.isActive, true)))
    .returning({ id: products.id });
  if (!rows.length) throw new ProductNotFoundError(`Product ${productId} not found or already inactive`);
  return { status: "ok", product_id: productId };
}

export interface Resolution {
  candidateCount: number;
  product: ProductRow | null; // the single active match, or null when 0 or >1
  candidates: ProductRow[];
}

// Resolve a product reference to its ACTIVE candidates. An exact (case-insensitive)
// SKU match wins as the single candidate; otherwise a name substring match over
// active products is collected and counted. 0 or >1 is not deterministic.
export async function resolveActiveProduct(productRef: string): Promise<Resolution> {
  const ref = (productRef || "").trim();
  if (!ref) return { candidateCount: 0, product: null, candidates: [] };

  const exact = await db
    .select()
    .from(products)
    .where(and(eq(products.isActive, true), sql`lower(${products.sku}) = lower(${ref})`));
  if (exact.length === 1) return { candidateCount: 1, product: exact[0], candidates: exact };

  const byName = await db
    .select()
    .from(products)
    .where(and(eq(products.isActive, true), ilike(products.name, `%${ref}%`)))
    .orderBy(asc(products.name));
  const count = byName.length;
  return { candidateCount: count, product: count === 1 ? byName[0] : null, candidates: byName };
}
