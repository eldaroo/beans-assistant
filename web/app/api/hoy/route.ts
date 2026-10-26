// GET /api/hoy — the Hoy dashboard snapshot: headline numbers plus the attention
// signals (overdue arrivals, overdue supplier check-ins, pending customs), all
// derived from stored data.
import { guard } from "@/lib/api-auth";
import { ok, fail } from "@/lib/http";
import { dashboardSnapshot } from "@/lib/domains/analytics";
import { listProducts } from "@/lib/domains/products";
import { countActive } from "@/lib/domains/suppliers";
import { attentionSnapshot } from "@/lib/domains/command-center";

export async function GET() {
  const g = await guard();
  if (g) return g;
  try {
    const [snap, products, suppliers, attention] = await Promise.all([
      dashboardSnapshot(),
      listProducts(),
      countActive(),
      attentionSnapshot(),
    ]);
    return ok({
      revenue_usd: snap.revenueUsd,
      profit_usd: snap.profitUsd,
      recent_days: snap.recentDays,
      product_count: products.length,
      supplier_count: suppliers,
      // The attention block is the same aggregation the internal business_status endpoint
      // returns (lib/domains/command-center attentionSnapshot); the chat's "what needs
      // attention" list is byte-equal to the command-center home's (spec 010 T-010, AC6).
      attention,
    });
  } catch (e) {
    return fail("read_failed", (e as Error).message, 500);
  }
}
