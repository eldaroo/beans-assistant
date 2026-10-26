// POST /api/internal/ops/read_revenue — the internal read behind the MCP read_revenue tool
// (spec 010 M2, T-007, s-02). Service-token authenticated (internalGuard), tenant pinned out
// of band, read-plus-propose only: this family never commits. Returns the flat `revenue` key
// the MCP tool lifts ({ ok:true, revenue }), not the session envelope's nested `data`.
import { NextResponse } from "next/server";
import { internalGuard } from "@/lib/internal-auth";
import { fail, requireDb } from "@/lib/http";
import { auditToolCall } from "@/lib/audit";
import { revenuePaidCents } from "@/lib/domains/analytics";
import { centsToUsd } from "@/lib/money";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const g = internalGuard(req.headers);
  if (!g.ok) return fail(g.code, g.message, g.status);
  const dbErr = requireDb();
  if (dbErr) return dbErr;
  try {
    const cents = await revenuePaidCents();
    await auditToolCall("read_revenue");
    return NextResponse.json({ ok: true, revenue: { revenue_cents: cents, revenue_usd: centsToUsd(cents) } });
  } catch (e) {
    // The error.message is lifted into MODEL-visible tool output by the MCP callRead, so it
    // returns a generic message and logs the raw cause server-side only (Tamir, council M1).
    console.error("read_revenue internal read failed:", (e as Error).message);
    return fail("read_failed", "No pude leer los ingresos", 500);
  }
}
