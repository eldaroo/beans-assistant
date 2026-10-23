// Append-only audit log + per-session tool-call rate caps. Ported from
// backend/services/ops_guard.py (spec 007 AC12) onto the single-business
// audit_log table. "session" is the single business here.
//
// The caps are a floor against a hijacked model or a runaway loop spamming the
// write API; generous for normal use, tight only where a write is destructive.

import { and, count, gte, inArray } from "drizzle-orm";
import { db } from "@/lib/db";
import { auditLog } from "@/db/schema";

const WINDOW_SECONDS = 60;
const GLOBAL_CAP = 60; // all write intents per window
const DESTRUCTIVE_CAP = 8; // cancel_* / deactivate per window (tighter)
export const DESTRUCTIVE_OPS = new Set<string>([
  "cancel_last_operation",
  "cancel_sale",
  "cancel_expense",
  "cancel_stock_movement",
  "deactivate_product",
]);

function isoNow(): string {
  return new Date().toISOString();
}

function isoSince(seconds: number): string {
  return new Date(Date.now() - seconds * 1000).toISOString();
}

// Append one audit row. Never throws into the caller (a lost audit row must not
// sink a real operation, but it is logged).
export async function appendAudit(params: {
  name: string;
  args?: unknown;
  caller?: string;
  opToken?: string | null;
  outcome?: string;
}): Promise<void> {
  const { name, args, caller = "app", opToken = null, outcome = "ok" } = params;
  try {
    await db.insert(auditLog).values({
      name,
      args: args !== undefined && args !== null ? JSON.stringify(args) : null,
      caller,
      opToken,
      outcome,
      createdAt: isoNow(),
    });
  } catch (err) {
    console.error("audit_log append failed (non-fatal)", err);
  }
}

// True if a call to opName is within the per-session window caps. Counts prior
// audit rows in the window; the destructive cap is checked against destructive
// rows only. Fails CLOSED for destructive ops under DB stress, open otherwise.
export async function withinCaps(opName: string): Promise<boolean> {
  const since = isoSince(WINDOW_SECONDS);
  try {
    const [{ c: total }] = await db
      .select({ c: count() })
      .from(auditLog)
      .where(gte(auditLog.createdAt, since));
    if (total >= GLOBAL_CAP) return false;
    if (DESTRUCTIVE_OPS.has(opName)) {
      const [{ c: dtotal }] = await db
        .select({ c: count() })
        .from(auditLog)
        .where(
          and(
            gte(auditLog.createdAt, since),
            inArray(auditLog.name, [...DESTRUCTIVE_OPS]),
          ),
        );
      if (dtotal >= DESTRUCTIVE_CAP) return false;
    }
    return true;
  } catch {
    return !DESTRUCTIVE_OPS.has(opName);
  }
}
