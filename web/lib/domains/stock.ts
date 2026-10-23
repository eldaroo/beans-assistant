// Stock domain. Ported from backend/services/stock_service.py + the stock_current
// view. Stock-on-hand is the signed sum of movements (IN/ADJUSTMENT add, OUT subtract).

import { eq, sql } from "drizzle-orm";
import { db } from "@/lib/db";
import { stockMovements } from "@/db/schema";

export interface StockCurrentRow {
  product_id: number;
  sku: string;
  name: string;
  stock_qty: number;
}

export async function currentStock(): Promise<StockCurrentRow[]> {
  const res = await db.execute(
    sql`SELECT product_id, sku, name, stock_qty FROM stock_current ORDER BY name`,
  );
  return (res.rows as unknown[] as StockCurrentRow[]).map((r) => ({
    ...r,
    stock_qty: Number(r.stock_qty),
  }));
}

export async function stockForProduct(productId: number): Promise<number> {
  const res = await db.execute(
    sql`SELECT COALESCE(SUM(CASE WHEN movement_type IN ('IN','ADJUSTMENT') THEN quantity
             WHEN movement_type = 'OUT' THEN -quantity ELSE 0 END), 0) AS qty
        FROM stock_movements WHERE product_id = ${productId}`,
  );
  return Number((res.rows[0] as { qty: number | string }).qty);
}

// Record a stock movement. ADD_STOCK is one of the reversible, auto-postable ops.
export async function addStock(params: {
  productId: number;
  quantity: number;
  reason?: string;
  movementType?: "IN" | "OUT" | "ADJUSTMENT";
  reference?: string | null;
}): Promise<{ status: string; movement_id: number }> {
  const { productId, quantity, reason = "Stock update", movementType = "IN", reference = null } = params;
  // Never let an unresolved product reach the insert (it would send product_id
  // DEFAULT and fail the NOT NULL/FK with a raw DB error). Fail with a clear message.
  if (productId == null) throw new Error("No se resolvio el producto para el movimiento de stock");
  const [row] = await db
    .insert(stockMovements)
    .values({ productId, movementType, quantity, reason, reference })
    .returning({ id: stockMovements.id });
  return { status: "ok", movement_id: row.id };
}

export async function cancelStockMovement(movementId: number): Promise<{ status: string }> {
  const rows = await db
    .delete(stockMovements)
    .where(eq(stockMovements.id, movementId))
    .returning({ id: stockMovements.id });
  if (!rows.length) throw new Error(`Stock movement ${movementId} not found`);
  return { status: "ok" };
}
