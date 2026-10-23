// GET /api/analytics — revenue (PAID), profit, and the daily sales summary.
import { guard } from "@/lib/api-auth";
import { ok, fail } from "@/lib/http";
import { revenuePaidCents, profitUsd, salesSummary } from "@/lib/domains/analytics";
import { centsToUsd } from "@/lib/money";

export async function GET() {
  const g = await guard();
  if (g) return g;
  try {
    const [revCents, profit, summary] = await Promise.all([revenuePaidCents(), profitUsd(), salesSummary(30)]);
    return ok({ revenue_usd: centsToUsd(revCents), profit_usd: profit, daily: summary });
  } catch (e) {
    return fail("read_failed", (e as Error).message, 500);
  }
}
