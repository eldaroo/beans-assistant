// GET /api/products — product catalog snapshot.
import { guard } from "@/lib/api-auth";
import { ok, fail } from "@/lib/http";
import { listProducts } from "@/lib/domains/products";

export async function GET(req: Request) {
  const g = await guard();
  if (g) return g;
  const includeInactive = new URL(req.url).searchParams.get("inactive") === "1";
  try {
    return ok(await listProducts({ includeInactive }));
  } catch (e) {
    return fail("read_failed", (e as Error).message, 500);
  }
}
