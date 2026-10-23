// GET /api/expenses — recent expenses.
import { guard } from "@/lib/api-auth";
import { ok, fail } from "@/lib/http";
import { listExpenses } from "@/lib/domains/expenses";

export async function GET(req: Request) {
  const g = await guard();
  if (g) return g;
  const limit = Number(new URL(req.url).searchParams.get("limit") ?? 100);
  try {
    return ok(await listExpenses({ limit }));
  } catch (e) {
    return fail("read_failed", (e as Error).message, 500);
  }
}
