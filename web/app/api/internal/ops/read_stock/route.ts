// POST /api/internal/ops/read_stock — the internal read endpoint behind the MCP read_stock
// tool (spec 010 M1, T-002, D-059). Authenticated by the service token (internalGuard), not a
// session: the beans-ai box reaches it over the internal-ops wire with the tenant pinned out of
// band. It delegates to the same domain read the session route uses and returns the result
// under the flat `stock` key the MCP tool lifts ({ ok:true, stock }), NOT the session
// envelope's nested `data` shape.
//
// Read-plus-propose only: this family never commits. The commit path stays session-only and
// rejects this token (M3, AC4). The tenant is validated present here; single-business scoping
// (one Beans) means the domain read needs no tenant arg yet — the pin is honored out of band so
// the shape is ready for a multi-business future without changing the tool contract.
import { NextResponse } from "next/server";
import { internalGuard } from "@/lib/internal-auth";
import { fail, requireDb } from "@/lib/http";
import { currentStock } from "@/lib/domains/stock";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const g = internalGuard(req.headers);
  if (!g.ok) return fail(g.code, g.message, g.status);
  const dbErr = requireDb();
  if (dbErr) return dbErr;
  try {
    const stock = await currentStock();
    // The MCP tool reads payload.stock directly (its resultKey), so this is a flat named result,
    // not ok(data). Errors still return the named-error envelope the MCP reads as error.message.
    return NextResponse.json({ ok: true, stock });
  } catch (e) {
    // This endpoint's error.message is lifted into MODEL-visible tool output by the MCP callRead,
    // so it returns a generic message and logs the raw cause server-side only, rather than
    // forwarding SQL/schema fragments to the model (Tamir, council M1).
    console.error("read_stock internal read failed:", (e as Error).message);
    return fail("read_failed", "No pude leer el stock", 500);
  }
}
