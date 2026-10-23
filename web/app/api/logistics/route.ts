// GET /api/logistics — shipping+customs lanes for the lead type across countries.
import { guard } from "@/lib/api-auth";
import { ok, fail } from "@/lib/http";
import { leadLanes } from "@/lib/domains/logistics";

export async function GET() {
  const g = await guard();
  if (g) return g;
  try {
    return ok(await leadLanes());
  } catch (e) {
    return fail("read_failed", (e as Error).message, 500);
  }
}
