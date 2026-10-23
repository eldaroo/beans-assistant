// Logistics domain. Ported from backend/services/logistics_service.py. The dedicated
// lens on the shipping + customs rows the landed cost also reads: a lane's total is a
// finished number only when BOTH are filled (a null is pending, never a real zero),
// and the pending-customs attention signal is computed from stored data, no message.

import { sql } from "drizzle-orm";
import { db } from "@/lib/db";
import { THREE_COUNTRIES, listBraceletTypes } from "@/lib/domains/costing";

export interface LogisticsLane {
  country: string;
  shippingCents: number | null;
  customsCents: number | null;
  shippingNote: string | null;
  customsNote: string | null;
  isComplete: boolean;
  totalCents: number | null;
  pendingLabels: string[];
  customsPending: boolean;
}

async function lane(productId: number, country: string): Promise<LogisticsLane> {
  const shipRes = await db.execute(
    sql`SELECT usd_amount_cents, note FROM shipping_lanes WHERE product_id = ${productId} AND country = ${country} ORDER BY id DESC LIMIT 1`,
  );
  const custRes = await db.execute(
    sql`SELECT usd_amount_cents, note FROM customs_duties WHERE product_id = ${productId} AND country = ${country} ORDER BY id DESC LIMIT 1`,
  );
  const ship = shipRes.rows[0] as { usd_amount_cents: number | null; note: string | null } | undefined;
  const cust = custRes.rows[0] as { usd_amount_cents: number | null; note: string | null } | undefined;
  const shippingCents = ship && ship.usd_amount_cents !== null ? Number(ship.usd_amount_cents) : null;
  const customsCents = cust && cust.usd_amount_cents !== null ? Number(cust.usd_amount_cents) : null;
  const isComplete = shippingCents !== null && customsCents !== null;
  const pendingLabels: string[] = [];
  if (shippingCents === null) pendingLabels.push("Envío");
  if (customsCents === null) pendingLabels.push("Aduana");
  return {
    country,
    shippingCents,
    customsCents,
    shippingNote: ship?.note ?? null,
    customsNote: cust?.note ?? null,
    isComplete,
    totalCents: isComplete ? (shippingCents as number) + (customsCents as number) : null,
    pendingLabels,
    customsPending: customsCents === null,
  };
}

export async function lanesFor(productId: number, countries = THREE_COUNTRIES): Promise<LogisticsLane[]> {
  const out: LogisticsLane[] = [];
  for (const c of countries) out.push(await lane(productId, c));
  return out;
}

export async function leadLanes(): Promise<LogisticsLane[] | null> {
  const types = await listBraceletTypes();
  if (!types.length) return null;
  return lanesFor(types[0].id);
}

export async function pendingCustoms(): Promise<LogisticsLane[]> {
  const lanes = await leadLanes();
  if (lanes === null) return [];
  return lanes.filter((ln) => ln.customsPending);
}
