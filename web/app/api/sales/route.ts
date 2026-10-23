// GET /api/sales — recent sales.
import { guard } from "@/lib/api-auth";
import { ok, fail } from "@/lib/http";
import { listSales } from "@/lib/domains/sales";

export async function GET(req: Request) {
  const g = await guard();
  if (g) return g;
  const limit = Number(new URL(req.url).searchParams.get("limit") ?? 50);
  try {
    return ok(await listSales({ limit }));
  } catch (e) {
    return fail("read_failed", (e as Error).message, 500);
  }
}
