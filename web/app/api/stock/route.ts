// GET /api/stock — current stock-on-hand per active product.
import { guard } from "@/lib/api-auth";
import { ok, fail } from "@/lib/http";
import { currentStock } from "@/lib/domains/stock";

export async function GET() {
  const g = await guard();
  if (g) return g;
  try {
    return ok(await currentStock());
  } catch (e) {
    return fail("read_failed", (e as Error).message, 500);
  }
}
