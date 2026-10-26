// POST /api/internal/ops/read_module — the internal read behind the MCP read_module tool
// (spec 010 M2, T-009, s-02). Service-token authenticated, read-plus-propose only. Body
// carries a non-tenant `module` id (one of the eight command-center modules); a module id
// outside the fixed set is a tool error (invalid_module), never a silent wrong read. Returns
// the flat `module` key the MCP tool lifts ({ ok:true, module }).
import { NextResponse } from "next/server";
import { internalGuard } from "@/lib/internal-auth";
import { fail, requireDb } from "@/lib/http";
import { MODULE_IDS, isModuleId, moduleSnapshot } from "@/lib/domains/command-center";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const g = internalGuard(req.headers);
  if (!g.ok) return fail(g.code, g.message, g.status);
  const dbErr = requireDb();
  if (dbErr) return dbErr;

  const body = (await req.json().catch(() => ({}))) as { module?: unknown };
  if (!isModuleId(body.module)) {
    return fail("invalid_module", `module must be one of: ${MODULE_IDS.join(", ")}`, 400);
  }

  try {
    const snapshot = await moduleSnapshot(body.module);
    return NextResponse.json({ ok: true, module: snapshot });
  } catch (e) {
    console.error("read_module internal read failed:", (e as Error).message);
    return fail("read_failed", "No pude leer el modulo", 500);
  }
}
