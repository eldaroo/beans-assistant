// Sales domain. Ported from backend/services/sales_service.py + database_pg.register_sale.
// A PAID sale validates stock-on-hand, derives line totals from the catalog price (or an
// explicit per-line price), and writes one stock OUT movement per item. The whole commit
// runs in one transaction so a sale is all-or-nothing.

import { and, desc, eq, ilike, or, sql } from "drizzle-orm";
import { db } from "@/lib/db";
import { sales, saleItems, products, stockMovements } from "@/db/schema";
import { centsToUsd } from "@/lib/money";

export type SaleStatus = "PAID" | "PENDING" | "CANCELLED";

export interface SaleItemInput {
  productId?: number;
  productRef?: string; // sku or name substring
  quantity: number;
  unitPriceCents?: number; // overrides the catalog price
}

export interface RegisterSaleInput {
  items: SaleItemInput[];
  status?: SaleStatus;
  customerName?: string | null;
}

export async function registerSale(input: RegisterSaleInput): Promise<{
  status: string;
  sale_id: number;
  total_usd: number | null;
}> {
  const status: SaleStatus = input.status ?? "PAID";
  if (!input.items?.length) throw new Error("A sale must include at least one item");

  return db.transaction(async (tx) => {
    // 1. Resolve each item to a product_id.
    const resolved: Array<SaleItemInput & { productId: number }> = [];
    for (const it of input.items) {
      let productId = it.productId;
      if (productId == null) {
        const ref = it.productRef;
        if (!ref) throw new Error("Each item must include productId or productRef");
        const found = await tx
          .select({ id: products.id })
          .from(products)
          .where(or(eq(products.sku, ref), ilike(products.name, `%${ref}%`)))
          .limit(1);
        if (!found.length) throw new Error(`Unknown product reference: ${ref}`);
        productId = found[0].id;
      }
      resolved.push({ ...it, productId });
    }

    // 2. Validate stock for a PAID sale.
    if (status === "PAID") {
      for (const it of resolved) {
        const r = await tx.execute(
          sql`SELECT p.name, COALESCE(s.stock_qty, 0) AS stock_qty
              FROM products p LEFT JOIN stock_current s ON p.id = s.product_id
              WHERE p.id = ${it.productId}`,
        );
        const row = r.rows[0] as { name: string; stock_qty: number | string } | undefined;
        if (!row) throw new Error(`Producto con ID ${it.productId} no encontrado`);
        const available = Number(row.stock_qty);
        if (available < it.quantity) {
          throw new Error(
            `No hay suficiente stock de ${row.name}. Disponible: ${available} unidades, solicitado: ${it.quantity} unidades`,
          );
        }
      }
    }

    // 3. Line totals (explicit price, else catalog price).
    let totalCents = 0;
    const enriched: Array<{ productId: number; quantity: number; unitPriceCents: number; lineTotalCents: number }> = [];
    for (const it of resolved) {
      let price = it.unitPriceCents;
      if (price == null) {
        const [pr] = await tx
          .select({ price: products.unitPriceCents })
          .from(products)
          .where(eq(products.id, it.productId))
          .limit(1);
        if (!pr || pr.price == null) {
          throw new Error(`El producto ${it.productId} no tiene precio de venta cargado`);
        }
        price = pr.price;
      }
      const lineTotal = price * it.quantity;
      totalCents += lineTotal;
      enriched.push({ productId: it.productId, quantity: it.quantity, unitPriceCents: price, lineTotalCents: lineTotal });
    }

    // 4. Insert the sale.
    const saleNumber = `S-${Date.now()}${String(Math.floor(Math.random() * 1e6)).padStart(6, "0")}`;
    const [sale] = await tx
      .insert(sales)
      .values({
        saleNumber,
        totalAmountCents: totalCents,
        status,
        customerName: input.customerName ?? null,
        ...(status === "PAID" ? { paidAt: new Date() } : {}),
      })
      .returning({ id: sales.id });

    // 5. Items + stock OUT movements for a PAID sale.
    for (const it of enriched) {
      await tx.insert(saleItems).values({
        saleId: sale.id,
        productId: it.productId,
        quantity: it.quantity,
        unitPriceCents: it.unitPriceCents,
        lineTotalCents: it.lineTotalCents,
      });
      if (status === "PAID") {
        await tx.insert(stockMovements).values({
          productId: it.productId,
          movementType: "OUT",
          quantity: it.quantity,
          reason: "Sale",
        });
      }
    }

    return { status: "ok", sale_id: sale.id, total_usd: centsToUsd(totalCents) };
  });
}

export type SaleRow = typeof sales.$inferSelect;

export async function listSales(opts: { limit?: number; offset?: number } = {}): Promise<SaleRow[]> {
  const { limit = 50, offset = 0 } = opts;
  return db.select().from(sales).orderBy(desc(sales.createdAt), desc(sales.id)).limit(limit).offset(offset);
}

export async function getSaleWithItems(saleId: number) {
  const [sale] = await db.select().from(sales).where(eq(sales.id, saleId)).limit(1);
  if (!sale) throw new Error(`Sale ${saleId} not found`);
  const items = await db.select().from(saleItems).where(eq(saleItems.saleId, saleId));
  return { ...sale, items };
}

// Cancel a sale: mark CANCELLED and reverse the stock it consumed (append IN
// movements), all-or-nothing. Idempotent on an already-cancelled sale.
export async function cancelSale(saleId: number): Promise<{ status: string; sale_id: number }> {
  return db.transaction(async (tx) => {
    const [sale] = await tx.select().from(sales).where(eq(sales.id, saleId)).limit(1);
    if (!sale) throw new Error(`Sale ${saleId} not found`);
    if (sale.status === "CANCELLED") return { status: "ok", sale_id: saleId };
    const items = await tx.select().from(saleItems).where(eq(saleItems.saleId, saleId));
    await tx.update(sales).set({ status: "CANCELLED" }).where(eq(sales.id, saleId));
    if (sale.status === "PAID") {
      for (const it of items) {
        await tx.insert(stockMovements).values({
          productId: it.productId,
          movementType: "IN",
          quantity: it.quantity,
          reason: `Sale cancel #${saleId}`,
        });
      }
    }
    return { status: "ok", sale_id: saleId };
  });
}
