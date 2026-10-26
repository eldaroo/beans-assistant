// POST /api/internal/ops/read_profit — the internal read behind the MCP read_profit tool
// (spec 010 M2, T-007, s-02). Service-token authenticated, read-plus-propose only. Profit is
// revenue (PAID sales) minus net expenses, derived in the DB (profit_summary view), never from
// the model. Returns the flat `profit` key the MCP tool lifts ({ ok:true, profit }).
import { NextResponse } from "next/server";
import { internalGuard } from "@/lib/internal-auth";
import { fail, requireDb } from "@/lib/http";
import { auditToolCall } from "@/lib/audit";
import { profitUsd } from "@/lib/domains/analytics";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const g = internalGuard(req.headers);
  if (!g.ok) return fail(g.code, g.message, g.status);
  const dbErr = requireDb();
  if (dbErr) return dbErr;
  try {
    const profit = await profitUsd();
    await auditToolCall("read_profit");
    return NextResponse.json({ ok: true, profit: { profit_usd: profit } });
  } catch (e) {
    console.error("read_profit internal read failed:", (e as Error).message);
    return fail("read_failed", "No pude leer la ganancia", 500);
  }
}
