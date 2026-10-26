// POST /api/internal/ops/read_sales_summary — the internal read behind the MCP
// read_sales_summary tool (spec 010 M2, T-008, s-02). Service-token authenticated,
// read-plus-propose only. Body carries an optional non-tenant `limit` (how many recent days,
// 1 to 50, default 10) — never a tenant, never an amount the model invents. Returns the flat
// `sales_summary` key the MCP tool lifts ({ ok:true, sales_summary }).
import { NextResponse } from "next/server";
import { internalGuard } from "@/lib/internal-auth";
import { fail, requireDb } from "@/lib/http";
import { auditToolCall } from "@/lib/audit";
import { salesSummary } from "@/lib/domains/analytics";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const g = internalGuard(req.headers);
  if (!g.ok) return fail(g.code, g.message, g.status);
  const dbErr = requireDb();
  if (dbErr) return dbErr;

  // Clamp the model-supplied limit to the tool's declared range (1..50). A missing or
  // non-numeric limit falls back to 10; an out-of-range value is clamped, not refused, so a
  // slightly-wrong tool arg still answers rather than dead-ending.
  let limit = 10;
  const body = (await req.json().catch(() => ({}))) as { limit?: unknown };
  const raw = Number(body.limit);
  if (Number.isFinite(raw)) limit = Math.min(50, Math.max(1, Math.trunc(raw)));

  try {
    const sales_summary = await salesSummary(limit);
    await auditToolCall("read_sales_summary");
    return NextResponse.json({ ok: true, sales_summary });
  } catch (e) {
    console.error("read_sales_summary internal read failed:", (e as Error).message);
    return fail("read_failed", "No pude leer el resumen de ventas", 500);
  }
}
