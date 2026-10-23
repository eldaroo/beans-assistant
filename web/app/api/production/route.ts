// GET /api/production — per-country latest week plus the company-wide rollup.
import { guard } from "@/lib/api-auth";
import { ok, fail } from "@/lib/http";
import { currentWeek, perCountry } from "@/lib/domains/production";

export async function GET() {
  const g = await guard();
  if (g) return g;
  try {
    const [rollup, byCountry] = await Promise.all([currentWeek(), perCountry()]);
    return ok({ rollup, by_country: byCountry });
  } catch (e) {
    return fail("read_failed", (e as Error).message, 500);
  }
}
