// Suppliers domain. Ported from backend/services/supplier_service.py. The directory
// plus the overdue-check-in attention signal (AC13), computed from stored data with
// no message sent. A supplier with no recorded check-in yet is NOT overdue; overdue
// is an active supplier whose last check-in is strictly older than the window.

import { asc, count, eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { suppliers } from "@/db/schema";

export const CHECKIN_WINDOW_DAYS = 14;

export type SupplierRow = typeof suppliers.$inferSelect;

export interface SupplierStatus {
  id: number;
  name: string;
  country: string | null;
  contact: string | null;
  isActive: boolean;
  lastCheckinAt: string | null;
  isOverdue: boolean;
  daysSinceCheckin: number | null;
}

function daysSince(lastCheckinAt: Date | string | null, today: Date): number | null {
  if (!lastCheckinAt) return null;
  const d = new Date(lastCheckinAt);
  if (Number.isNaN(d.getTime())) return null;
  const dUtc = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  return Math.floor((today.getTime() - dUtc) / 86400000);
}

function utcToday(): Date {
  const n = new Date();
  return new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), n.getUTCDate()));
}

function statusFrom(row: SupplierRow, today: Date, windowDays: number): SupplierStatus {
  const days = daysSince(row.lastCheckinAt, today);
  return {
    id: row.id,
    name: row.name,
    country: row.country,
    contact: row.contact,
    isActive: row.isActive,
    lastCheckinAt: row.lastCheckinAt ? new Date(row.lastCheckinAt).toISOString() : null,
    isOverdue: days !== null && days > windowDays,
    daysSinceCheckin: days,
  };
}

export async function directory(windowDays = CHECKIN_WINDOW_DAYS): Promise<SupplierStatus[]> {
  const today = utcToday();
  const rows = await db
    .select()
    .from(suppliers)
    .where(eq(suppliers.isActive, true))
    .orderBy(asc(suppliers.name));
  return rows.map((r) => statusFrom(r, today, windowDays));
}

export async function countActive(): Promise<number> {
  const [{ c }] = await db.select({ c: count() }).from(suppliers).where(eq(suppliers.isActive, true));
  return c;
}

export async function overdueCheckins(windowDays = CHECKIN_WINDOW_DAYS): Promise<SupplierStatus[]> {
  return (await directory(windowDays)).filter((s) => s.isOverdue);
}

export async function createSupplier(params: {
  name: string;
  country?: string | null;
  contact?: string | null;
}): Promise<{ status: string; supplier_id: number }> {
  const [row] = await db
    .insert(suppliers)
    .values({ name: params.name, country: params.country ?? null, contact: params.contact ?? null })
    .returning({ id: suppliers.id });
  return { status: "ok", supplier_id: row.id };
}

// Record a supplier check-in (reply) now, resetting the overdue cadence.
export async function recordCheckin(supplierId: number): Promise<{ status: string }> {
  const rows = await db
    .update(suppliers)
    .set({ lastCheckinAt: new Date() })
    .where(eq(suppliers.id, supplierId))
    .returning({ id: suppliers.id });
  if (!rows.length) throw new Error(`Supplier ${supplierId} not found`);
  return { status: "ok" };
}
