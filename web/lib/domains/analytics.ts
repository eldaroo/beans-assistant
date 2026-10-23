// Analytics domain. Ported from backend/services/analytics_service.py, reading the
// revenue_paid / expenses_total / profit_summary / sales_summary views. Profit is
// revenue (PAID sales) minus net expenses; every number is derived in the DB, never
// from the model.

import { sql } from "drizzle-orm";
import { db } from "@/lib/db";
import { centsToUsd } from "@/lib/money";

export async function revenuePaidCents(): Promise<number> {
  const res = await db.execute(sql`SELECT total_revenue_cents FROM revenue_paid`);
  return Number((res.rows[0] as { total_revenue_cents: number | string }).total_revenue_cents) || 0;
}

export async function profitUsd(): Promise<number> {
  const res = await db.execute(sql`SELECT profit_usd FROM profit_summary`);
  const v = (res.rows[0] as { profit_usd: number | string | null })?.profit_usd;
  return v == null ? 0 : Number(v);
}

export interface SalesSummaryRow {
  day: string;
  paid_sales_count: number;
  paid_revenue_cents: number;
  paid_revenue_usd: number | null;
}

export async function salesSummary(limitDays = 30): Promise<SalesSummaryRow[]> {
  const res = await db.execute(
    sql`SELECT day, paid_sales_count, paid_revenue_cents
        FROM sales_summary ORDER BY day DESC LIMIT ${limitDays}`,
  );
  return (res.rows as Array<{ day: string; paid_sales_count: number | string; paid_revenue_cents: number | string }>).map((r) => ({
    day: typeof r.day === "string" ? r.day : new Date(r.day as unknown as string).toISOString().slice(0, 10),
    paid_sales_count: Number(r.paid_sales_count),
    paid_revenue_cents: Number(r.paid_revenue_cents),
    paid_revenue_usd: centsToUsd(Number(r.paid_revenue_cents)),
  }));
}

// A compact snapshot for the dashboard (Hoy): revenue, profit, and today's sales.
export async function dashboardSnapshot(): Promise<{
  revenueUsd: number | null;
  profitUsd: number;
  recentDays: SalesSummaryRow[];
}> {
  const [revCents, profit, summary] = await Promise.all([
    revenuePaidCents(),
    profitUsd(),
    salesSummary(14),
  ]);
  return { revenueUsd: centsToUsd(revCents), profitUsd: profit, recentDays: summary };
}
