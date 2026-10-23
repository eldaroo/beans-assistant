// GET /api/hoy — the Hoy dashboard snapshot: headline numbers plus the attention
// signals (overdue arrivals, overdue supplier check-ins, pending customs), all
// derived from stored data.
import { guard } from "@/lib/api-auth";
import { ok, fail } from "@/lib/http";
import { dashboardSnapshot } from "@/lib/domains/analytics";
import { listProducts } from "@/lib/domains/products";
import { overdueArrivals } from "@/lib/domains/production";
import { overdueCheckins, countActive } from "@/lib/domains/suppliers";
import { pendingCustoms } from "@/lib/domains/logistics";

export async function GET() {
  const g = await guard();
  if (g) return g;
  try {
    const [snap, products, arrivals, checkins, suppliers, customs] = await Promise.all([
      dashboardSnapshot(),
      listProducts(),
      overdueArrivals(),
      overdueCheckins(),
      countActive(),
      pendingCustoms(),
    ]);
    return ok({
      revenue_usd: snap.revenueUsd,
      profit_usd: snap.profitUsd,
      recent_days: snap.recentDays,
      product_count: products.length,
      supplier_count: suppliers,
      attention: {
        overdue_arrivals: arrivals,
        overdue_checkins: checkins,
        pending_customs: customs,
      },
    });
  } catch (e) {
    return fail("read_failed", (e as Error).message, 500);
  }
}
