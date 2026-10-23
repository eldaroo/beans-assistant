// Production domain. Ported from backend/services/production_service.py +
// production_repository.py. Units produced this week vs target, and the overdue
// arrival-cadence signal (computed from stored data, no message sent). A blank or
// unparseable expected date is never overdue; genuine-but-tiny progress floors to
// 1%, never a false 0% while real units exist.

import { sql } from "drizzle-orm";
import { db } from "@/lib/db";
import { productionRecords } from "@/db/schema";

export function normalizeWeek(periodWeek: string): string {
  const m = /^(\d{4})-W?(\d{1,2})$/.exec(String(periodWeek).trim());
  if (!m) throw new Error(`period_week must be YYYY-Www: ${periodWeek}`);
  return `${m[1]}-W${String(Number(m[2])).padStart(2, "0")}`;
}

interface RawRow {
  product_id: number | null;
  country: string | null;
  period_week: string;
  units_produced: number | string | null;
  units_target: number | string | null;
  expected_next_at: string | null;
}

export interface ProductionStatus {
  country: string | null;
  periodWeek: string;
  unitsProduced: number;
  unitsTarget: number | null;
  expectedNextAt: string | null;
  isOverdue: boolean;
  hasTarget: boolean;
  pctOfTarget: number | null;
  meetsTarget: boolean;
}

function isOverdue(expectedNextAt: string | null, today: Date): boolean {
  if (!expectedNextAt) return false;
  const due = new Date(String(expectedNextAt).slice(0, 10) + "T00:00:00Z");
  if (Number.isNaN(due.getTime())) return false;
  return due.getTime() <= today.getTime();
}

function statusFrom(row: RawRow, today: Date): ProductionStatus {
  const unitsProduced = Number(row.units_produced || 0);
  const unitsTarget = row.units_target == null ? null : Number(row.units_target);
  const hasTarget = unitsTarget != null && unitsTarget > 0;
  let pct: number | null = null;
  if (hasTarget) {
    pct = Math.round((100 * unitsProduced) / (unitsTarget as number));
    if (pct === 0 && unitsProduced > 0) pct = 1;
  }
  return {
    country: row.country,
    periodWeek: row.period_week,
    unitsProduced,
    unitsTarget,
    expectedNextAt: row.expected_next_at,
    isOverdue: isOverdue(row.expected_next_at, today),
    hasTarget,
    pctOfTarget: pct,
    meetsTarget: hasTarget && unitsProduced >= (unitsTarget ?? 0),
  };
}

function utcToday(): Date {
  const n = new Date();
  return new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), n.getUTCDate()));
}

export async function recordProduction(params: {
  productId?: number | null;
  country: string;
  periodWeek: string;
  unitsProduced: number;
  unitsTarget?: number | null;
  expectedNextAt?: string | null;
}): Promise<void> {
  await db.insert(productionRecords).values({
    productId: params.productId ?? null,
    country: params.country,
    periodWeek: normalizeWeek(params.periodWeek),
    unitsProduced: params.unitsProduced,
    unitsTarget: params.unitsTarget ?? null,
    expectedNextAt: params.expectedNextAt ?? null,
  });
}

// Latest (newest id) record for one country.
export async function currentWeek(country?: string | null): Promise<ProductionStatus | null> {
  const today = utcToday();
  if (country != null) {
    const res = await db.execute(sql`
      SELECT product_id, country, period_week, units_produced, units_target, expected_next_at
      FROM production_records WHERE country = ${country} ORDER BY id DESC LIMIT 1`);
    const row = res.rows[0] as unknown as RawRow | undefined;
    return row ? statusFrom(row, today) : null;
  }
  // Home rollup: newest week across countries, units + target summed over the
  // newest record per country (so a same-week correction is not double-counted).
  const wkRes = await db.execute(sql`SELECT MAX(period_week) AS w FROM production_records`);
  const week = (wkRes.rows[0] as { w: string | null })?.w;
  if (!week) return null;
  const rollRes = await db.execute(sql`
    SELECT COALESCE(SUM(p.units_produced), 0) AS units,
           SUM(p.units_target) AS target
    FROM production_records p
    WHERE p.period_week = ${week}
      AND p.id = (SELECT x.id FROM production_records x
                  WHERE x.country = p.country AND x.period_week = p.period_week
                  ORDER BY x.id DESC LIMIT 1)`);
  const roll = rollRes.rows[0] as { units: number | string; target: number | string | null };
  return {
    country: null,
    periodWeek: week,
    unitsProduced: Number(roll.units || 0),
    unitsTarget: roll.target == null ? null : Number(roll.target),
    expectedNextAt: null,
    isOverdue: false,
    hasTarget: roll.target != null && Number(roll.target) > 0,
    pctOfTarget:
      roll.target != null && Number(roll.target) > 0
        ? Math.max(Number(roll.units) > 0 ? 1 : 0, Math.round((100 * Number(roll.units)) / Number(roll.target)))
        : null,
    meetsTarget: roll.target != null && Number(roll.units) >= Number(roll.target),
  };
}

export async function perCountry(): Promise<ProductionStatus[]> {
  const today = utcToday();
  const res = await db.execute(sql`
    SELECT p.product_id, p.country, p.period_week, p.units_produced, p.units_target, p.expected_next_at
    FROM production_records p
    WHERE p.id = (SELECT x.id FROM production_records x
                  WHERE x.country = p.country ORDER BY x.id DESC LIMIT 1)
    ORDER BY p.country`);
  return (res.rows as unknown as RawRow[]).map((r) => statusFrom(r, today));
}

export async function overdueArrivals(): Promise<ProductionStatus[]> {
  return (await perCountry()).filter((s) => s.isOverdue);
}
