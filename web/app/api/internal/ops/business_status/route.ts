// POST /api/internal/ops/business_status — the internal read behind the MCP business_status
// tool (spec 010 M2, T-010, s-02, AC6). Service-token authenticated, read-plus-propose only.
// Returns the one prioritized "what needs attention today" aggregation across the business,
// under the flat `attention` key the MCP tool lifts ({ ok:true, attention }).
//
// It is byte-equal to the Hoy command-center home's attention aggregation by construction:
// GET /api/hoy and this endpoint both call attentionSnapshot() (lib/domains/command-center),
// so the model's "what needs attention" list is the same list the owner sees on the home — the
// MCP tool's "never invent items" promise is enforced by a single source, not by duplicated code.
import { NextResponse } from "next/server";
import { internalGuard } from "@/lib/internal-auth";
import { fail, requireDb } from "@/lib/http";
import { attentionSnapshot } from "@/lib/domains/command-center";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const g = internalGuard(req.headers);
  if (!g.ok) return fail(g.code, g.message, g.status);
  const dbErr = requireDb();
  if (dbErr) return dbErr;
  try {
    const attention = await attentionSnapshot();
    return NextResponse.json({ ok: true, attention });
  } catch (e) {
    console.error("business_status internal read failed:", (e as Error).message);
    return fail("read_failed", "No pude leer el estado del negocio", 500);
  }
}
