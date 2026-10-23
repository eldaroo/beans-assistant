// Costing domain. Ported from backend/services/costing_service.py +
// costing_repository.py (spec 003 M2-M4). Landed cost = sum of six components
// (materials, labor, packaging, shipping, customs, indirect). A pending component
// (cents null) is NEVER summed as zero; it is named and the total is "parcial".
// Margin is a real number only when the landed cost is complete AND a price is set.

import { sql } from "drizzle-orm";
import { db } from "@/lib/db";
import {
  bomLines,
  costInputs,
  inputPurchases,
  laborCosts,
  packagingCosts,
  shippingLanes,
  customsDuties,
  indirectCosts,
} from "@/db/schema";

export const STATUS_COMPLETE = "completo";
export const STATUS_PARTIAL = "parcial";

export const THREE_COUNTRIES = ["Colombia", "Armenia-Colombia", "Costa Rica"];

export const COMPONENT_ORDER: Array<[string, string]> = [
  ["materials", "Materiales"],
  ["labor", "Mano de obra"],
  ["packaging", "Empaque"],
  ["shipping", "Envío"],
  ["customs", "Aduana"],
  ["indirect", "Indirectos"],
];

export interface CostComponent {
  key: string;
  label: string;
  cents: number | null; // null = pending, excluded from the total
  detail: string;
}

export interface LandedCost {
  productId: number;
  productName: string;
  country: string;
  components: CostComponent[];
  totalCents: number;
  status: string;
  pendingLabels: string[];
  isComplete: boolean;
}

export interface Margin {
  country: string;
  landed: LandedCost;
  priceCents: number | null;
  marginCents: number | null;
  pendingReason: string | null;
}

export interface CountryComparison {
  productId: number;
  productName: string;
  margins: Margin[];
  lowestCompleteCountry: string | null;
}

// ------------------------------------------------------------------ pure core

// Map an ISO YYYY-Www week to its calendar month YYYY-MM by the week's Thursday
// (the ISO-8601 rule that fixes which year/month a week belongs to).
export function monthOfIsoWeek(periodWeek: string): string {
  const m = /^(\d{4})-W(\d{1,2})$/.exec(String(periodWeek).trim());
  if (!m) throw new Error(`period_week must be ISO 'YYYY-Www': ${periodWeek}`);
  const year = Number(m[1]);
  const week = Number(m[2]);
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const dow = (jan4.getUTCDay() + 6) % 7; // Mon=0
  const thursday = new Date(jan4);
  thursday.setUTCDate(jan4.getUTCDate() - dow + (week - 1) * 7 + 3);
  return `${thursday.getUTCFullYear()}-${String(thursday.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function unitsInMonth(
  weeklyRows: Array<{ period_week: string; units: number }>,
  periodMonth: string,
): number {
  let total = 0;
  for (const row of weeklyRows) {
    if (monthOfIsoWeek(row.period_week) === periodMonth) total += Number(row.units || 0);
  }
  return total;
}

// Direct labor per unit on a COMPLETED basis: payment / units COMPLETED, so a
// short batch raises per-unit labor. null when no completed batch (pending).
export function laborPerUnit(batchPaymentCents: number, unitsCompleted: number): number | null {
  if (!unitsCompleted) return null;
  return Math.round(batchPaymentCents / unitsCompleted);
}

// Sum filled components; a pending one (cents null) is excluded, never zero.
// overrides maps a key to a cents value, or null to force pending (scenario path).
export function recompute(
  components: CostComponent[],
  overrides: Record<string, number | null> = {},
): { resolved: CostComponent[]; totalCents: number; status: string; pendingLabels: string[] } {
  const resolved: CostComponent[] = [];
  let total = 0;
  const pending: string[] = [];
  for (const c of components) {
    const cents = Object.prototype.hasOwnProperty.call(overrides, c.key) ? overrides[c.key] : c.cents;
    const rc: CostComponent = { key: c.key, label: c.label, cents, detail: c.detail };
    resolved.push(rc);
    if (rc.cents !== null) total += Math.round(rc.cents);
    else pending.push(rc.label);
  }
  const status = pending.length ? STATUS_PARTIAL : STATUS_COMPLETE;
  return { resolved, totalCents: total, status, pendingLabels: pending };
}

function asCents(value: number | null | undefined): number | null {
  return value === null || value === undefined ? null : Math.round(value);
}

// ------------------------------------------------------------- repository reads

async function materialsBreakdown(productId: number, country: string) {
  const res = await db.execute(sql`
    SELECT b.cost_input_id AS cost_input_id, ci.name AS name, b.quantity AS quantity,
           (SELECT ip.usd_amount_cents * 1.0 / ip.quantity
              FROM input_purchases ip
             WHERE ip.cost_input_id = b.cost_input_id AND ip.quantity > 0
             ORDER BY ip.purchased_at DESC, ip.id DESC LIMIT 1) AS unit_usd_cents
    FROM bom_lines b JOIN cost_inputs ci ON ci.id = b.cost_input_id
    WHERE b.product_id = ${productId} AND b.country = ${country}
    ORDER BY ci.name`);
  return res.rows as Array<{ name: string; quantity: number | string; unit_usd_cents: number | string | null }>;
}

async function materials(productId: number, country: string): Promise<[number | null, string]> {
  const rows = await materialsBreakdown(productId, country);
  if (!rows.length) return [null, "sin receta (BOM) cargada"];
  const missing = rows.filter((r) => r.unit_usd_cents === null).map((r) => r.name);
  if (missing.length) return [null, "falta precio de: " + missing.join(", ")];
  const total = rows.reduce((s, r) => s + Number(r.quantity) * Number(r.unit_usd_cents), 0);
  return [Math.round(total), rows.map((r) => r.name).join(", ")];
}

async function latestRow<T>(query: ReturnType<typeof sql>): Promise<T | null> {
  const res = await db.execute(query);
  return (res.rows[0] as T) ?? null;
}

async function indirectPerUnit(country: string): Promise<[number | null, string]> {
  const pool = await latestRow<{ period_month: string; pool_cents: number | string }>(
    sql`SELECT period_month, pool_cents FROM indirect_costs WHERE country = ${country} ORDER BY period_month DESC, id DESC LIMIT 1`,
  );
  if (!pool) return [null, "sin pool indirecto cargado"];
  const weeklyRes = await db.execute(sql`
    SELECT p.period_week AS period_week, p.units_produced AS units
    FROM production_records p
    WHERE p.country = ${country}
      AND p.id = (SELECT x.id FROM production_records x
                  WHERE x.country = p.country AND x.period_week = p.period_week
                  ORDER BY x.id DESC LIMIT 1)
    ORDER BY p.period_week DESC`);
  const weekly = weeklyRes.rows as Array<{ period_week: string; units: number | string }>;
  const units = unitsInMonth(
    weekly.map((w) => ({ period_week: w.period_week, units: Number(w.units) })),
    pool.period_month,
  );
  if (!units) return [null, `sin producción registrada en ${pool.period_month}`];
  const perUnit = Math.round(Number(pool.pool_cents) / units);
  return [perUnit, `exhibidores + overhead, ${pool.period_month} (${units} u)`];
}

async function buildComponents(productId: number, country: string): Promise<CostComponent[]> {
  const [materialsCents, materialsDetail] = await materials(productId, country);

  const lab = await latestRow<{ batch_payment_cents: number; units_completed: number }>(
    sql`SELECT batch_payment_cents, units_completed FROM labor_costs WHERE product_id = ${productId} AND country = ${country} ORDER BY recorded_at DESC, id DESC LIMIT 1`,
  );
  const laborCents = lab ? laborPerUnit(Number(lab.batch_payment_cents), Number(lab.units_completed)) : null;
  const laborDetail = laborCents !== null ? `por unidad, lote de ${Number(lab!.units_completed)}` : "sin lote registrado";

  const pack = await latestRow<{ usd_amount_cents: number | null }>(
    sql`SELECT usd_amount_cents FROM packaging_costs WHERE product_id = ${productId} AND country = ${country} ORDER BY id DESC LIMIT 1`,
  );
  const packagingCents = pack ? asCents(pack.usd_amount_cents) : null;
  const packagingDetail = packagingCents !== null ? "por unidad" : "sin empaque cargado";

  const ship = await latestRow<{ usd_amount_cents: number | null; note: string | null }>(
    sql`SELECT usd_amount_cents, note FROM shipping_lanes WHERE product_id = ${productId} AND country = ${country} ORDER BY id DESC LIMIT 1`,
  );
  const shippingCents = ship && ship.usd_amount_cents !== null ? asCents(ship.usd_amount_cents) : null;
  const shippingDetail = ship && ship.note ? ship.note : "por averiguar";

  const cust = await latestRow<{ usd_amount_cents: number | null; note: string | null }>(
    sql`SELECT usd_amount_cents, note FROM customs_duties WHERE product_id = ${productId} AND country = ${country} ORDER BY id DESC LIMIT 1`,
  );
  const customsCents = cust && cust.usd_amount_cents !== null ? asCents(cust.usd_amount_cents) : null;
  const customsDetail = cust && cust.note ? cust.note : "por averiguar";

  const [indirectCents, indirectDetail] = await indirectPerUnit(country);

  const byKey: Record<string, CostComponent> = {
    materials: { key: "materials", label: "Materiales", cents: materialsCents, detail: materialsDetail },
    labor: { key: "labor", label: "Mano de obra", cents: laborCents, detail: laborDetail },
    packaging: { key: "packaging", label: "Empaque", cents: packagingCents, detail: packagingDetail },
    shipping: { key: "shipping", label: "Envío", cents: shippingCents, detail: shippingDetail },
    customs: { key: "customs", label: "Aduana", cents: customsCents, detail: customsDetail },
    indirect: { key: "indirect", label: "Indirectos", cents: indirectCents, detail: indirectDetail },
  };
  return COMPONENT_ORDER.map(([key]) => byKey[key]);
}

export async function landedCost(
  productId: number,
  country: string,
  overrides: Record<string, number | null> = {},
): Promise<LandedCost> {
  const prod = await latestRow<{ name: string }>(sql`SELECT name FROM products WHERE id = ${productId}`);
  const components = await buildComponents(productId, country);
  const { resolved, totalCents, status, pendingLabels } = recompute(components, overrides);
  return {
    productId,
    productName: prod?.name ?? String(productId),
    country,
    components: resolved,
    totalCents,
    status,
    pendingLabels,
    isComplete: status === STATUS_COMPLETE,
  };
}

export async function margin(
  productId: number,
  country: string,
  overrides: Record<string, number | null> = {},
): Promise<Margin> {
  const landed = await landedCost(productId, country, overrides);
  const priceRow = await latestRow<{ unit_price_cents: number | null }>(
    sql`SELECT unit_price_cents FROM products WHERE id = ${productId}`,
  );
  const price = priceRow?.unit_price_cents ?? null;
  if (price === null) {
    return { country, landed, priceCents: null, marginCents: null, pendingReason: "sin precio de venta" };
  }
  if (!landed.isComplete) {
    const faltan = landed.pendingLabels.map((l) => l.toLowerCase()).join(", ");
    return { country, landed, priceCents: price, marginCents: null, pendingReason: `costo parcial · falta ${faltan}` };
  }
  return { country, landed, priceCents: price, marginCents: price - landed.totalCents, pendingReason: null };
}

export async function countryComparison(productId: number, countries = THREE_COUNTRIES): Promise<CountryComparison> {
  const margins: Margin[] = [];
  for (const c of countries) margins.push(await margin(productId, c));
  const complete = margins.filter((m) => m.landed.isComplete);
  const lowest = complete.length
    ? complete.reduce((a, b) => (b.landed.totalCents < a.landed.totalCents ? b : a)).country
    : null;
  return {
    productId,
    productName: margins[0]?.landed.productName ?? String(productId),
    margins,
    lowestCompleteCountry: lowest,
  };
}

export async function listBraceletTypes(): Promise<Array<{ id: number; sku: string; name: string }>> {
  const res = await db.execute(sql`
    SELECT DISTINCT p.id AS id, p.sku AS sku, p.name AS name
    FROM products p JOIN bom_lines b ON b.product_id = p.id
    WHERE p.is_active ORDER BY p.name`);
  return res.rows as Array<{ id: number; sku: string; name: string }>;
}

export async function leadLandedCost(overrides: Record<string, number | null> = {}): Promise<LandedCost | null> {
  const types = await listBraceletTypes();
  if (!types.length) return null;
  const countriesRes = await db.execute(
    sql`SELECT DISTINCT country FROM bom_lines WHERE product_id = ${types[0].id} ORDER BY country`,
  );
  const countries = (countriesRes.rows as Array<{ country: string }>).map((r) => r.country);
  if (!countries.length) return null;
  return landedCost(types[0].id, countries[0], overrides);
}

export async function countriesFor(productId: number): Promise<string[]> {
  const res = await db.execute(
    sql`SELECT DISTINCT country FROM bom_lines WHERE product_id = ${productId} ORDER BY country`,
  );
  return (res.rows as Array<{ country: string }>).map((r) => r.country);
}

export async function leadComparison(): Promise<CountryComparison | null> {
  const types = await listBraceletTypes();
  if (!types.length) return null;
  return countryComparison(types[0].id);
}

// ------------------------------------------------------------- write paths (M3)

// fx_rate is units of the original currency per 1 USD; usd = original / fx.
export function usdCentsFrom(originalAmountCents: number, fxRate: number): number {
  if (fxRate <= 0) throw new Error("fx_rate must be positive");
  return Math.round(originalAmountCents / fxRate);
}

export async function recordInputPurchase(params: {
  costInputId: number;
  originalCurrency: string;
  originalAmountCents: number;
  fxRate: number;
  quantity?: number;
  supplierId?: number | null;
  purchasedAt?: string | null;
}): Promise<number> {
  const usd = usdCentsFrom(params.originalAmountCents, params.fxRate);
  await db.insert(inputPurchases).values({
    costInputId: params.costInputId,
    supplierId: params.supplierId ?? null,
    originalCurrency: params.originalCurrency,
    originalAmountCents: params.originalAmountCents,
    fxRate: String(params.fxRate),
    usdAmountCents: usd,
    quantity: String(params.quantity ?? 1),
    ...(params.purchasedAt ? { purchasedAt: params.purchasedAt } : {}),
  });
  return usd;
}

export async function recordCostInput(name: string, category: string, unit = "u"): Promise<number> {
  const [row] = await db.insert(costInputs).values({ name, category, unit }).returning({ id: costInputs.id });
  return row.id;
}

export async function recordBomLine(productId: number, costInputId: number, country: string, quantity: number): Promise<void> {
  await db.insert(bomLines).values({ productId, costInputId, country, quantity: String(quantity) });
}

export async function recordPackagingCost(productId: number, country: string, usdAmountCents: number): Promise<void> {
  await db.insert(packagingCosts).values({ productId, country, usdAmountCents });
}

// Direct-labor batch over the units actually COMPLETED (AC11 completed basis).
export async function recordLaborBatch(productId: number, country: string, batchPaymentCents: number, unitsCompleted: number): Promise<void> {
  await db.insert(laborCosts).values({ productId, country, batchPaymentCents, unitsCompleted });
}

export async function recordShippingLane(productId: number, country: string, usdAmountCents: number | null = null, note: string | null = null): Promise<void> {
  await db.insert(shippingLanes).values({ productId, country, usdAmountCents, note });
}

export async function recordCustomsDuty(productId: number, country: string, usdAmountCents: number | null = null, note: string | null = null): Promise<void> {
  await db.insert(customsDuties).values({ productId, country, usdAmountCents, note });
}

export async function recordIndirectPool(country: string, periodMonth: string, poolCents: number): Promise<void> {
  await db.insert(indirectCosts).values({ country, periodMonth, poolCents });
}
