// GET /api/suppliers — active supplier directory with each one's check-in status.
import { guard } from "@/lib/api-auth";
import { ok, fail } from "@/lib/http";
import { directory } from "@/lib/domains/suppliers";

export async function GET() {
  const g = await guard();
  if (g) return g;
  try {
    return ok(await directory());
  } catch (e) {
    return fail("read_failed", (e as Error).message, 500);
  }
}
