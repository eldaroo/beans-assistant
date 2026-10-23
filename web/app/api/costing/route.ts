// GET /api/costing — landed-cost comparison across countries. ?product=<id> for a
// specific type, else the lead type. Null when no costable type exists yet.
import { guard } from "@/lib/api-auth";
import { ok, fail } from "@/lib/http";
import { countryComparison, leadComparison } from "@/lib/domains/costing";

export async function GET(req: Request) {
  const g = await guard();
  if (g) return g;
  const pid = new URL(req.url).searchParams.get("product");
  try {
    const data = pid ? await countryComparison(Number(pid)) : await leadComparison();
    return ok(data);
  } catch (e) {
    return fail("read_failed", (e as Error).message, 500);
  }
}
