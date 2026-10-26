// Append-only audit log + per-session tool-call rate caps. Ported from
// backend/services/ops_guard.py (spec 007 AC12) onto the single-business
// audit_log table. "session" is the single business here.
//
// The caps are a floor against a hijacked model or a runaway loop spamming the
// write API; generous for normal use, tight only where a write is destructive.

import { and, count, gte, inArray, isNull, ne, or } from "drizzle-orm";
import { db } from "@/lib/db";
import { auditLog } from "@/db/schema";
import { DESTRUCTIVE_OP_TYPES } from "@/lib/ops/registry";

const WINDOW_SECONDS = 60;
const GLOBAL_CAP = 60; // all write intents per window
const DESTRUCTIVE_CAP = 8; // cancel_* / deactivate per window (tighter)

// The pure cap decision (spec 010 M5, T-027): given the counts in the window, is one more call
// of this op allowed? Extracted from withinCaps so the arithmetic is testable without a DB. The
// global cap bounds all write intents; the tighter destructive cap bounds cancels/deactivations
// (DESTRUCTIVE_OPS) on TOP of the global one. Returns false at or above either applicable cap.
export function capDecision(
  windowTotal: number,
  windowDestructiveTotal: number,
  destructive: boolean,
  caps: { global?: number; destructive?: number } = {},
): boolean {
  const globalCap = caps.global ?? GLOBAL_CAP;
  const destructiveCap = caps.destructive ?? DESTRUCTIVE_CAP;
  if (windowTotal >= globalCap) return false;
  if (destructive && windowDestructiveTotal >= destructiveCap) return false;
  return true;
}

// The destructive write intents get the tighter cap and fail CLOSED. The names
// MUST match the operationType the stage path passes (uppercase) and the `name`
// column audit rows are written with, so the cap and the fail-closed branch
// actually fire. We reuse the registry's single source of truth rather than a
// hand-kept lowercase copy: an earlier copy here held the OLD Python op names
// (lowercase, and `cancel_stock_movement` vs the registry's `CANCEL_STOCK`), so
// the destructive cap never triggered and destructive ops failed OPEN under DB
// stress (spec 008 AC7 hardening; caught by m7-guards).
export const DESTRUCTIVE_OPS = DESTRUCTIVE_OP_TYPES;

export function isDestructive(opName: string): boolean {
  return DESTRUCTIVE_OPS.has((opName || "").toUpperCase());
}

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

// Audit one TOOL CALL (read or write), best-effort (spec 010 M5, T-027: "every tool call").
// Write intents are already audited inside stageOperation (caller "stage") / confirm / undo; this
// records the read-tool calls so the append-only log is a complete trail of what the box invoked,
// not only what it tried to write. appendAudit never throws, so a lost audit row cannot sink a
// real read. A read carries no op_token and no committing outcome.
export async function auditToolCall(name: string, caller = "read-tool"): Promise<void> {
  await appendAudit({ name, caller, outcome: "ok" });
}

// True if a call to opName is within the per-session window caps. Counts prior
// audit rows in the window; the destructive cap is checked against destructive
// rows only. Fails CLOSED for destructive ops under DB stress, open otherwise.
export async function withinCaps(opName: string): Promise<boolean> {
  const since = isoSince(WINDOW_SECONDS);
  try {
    // The GLOBAL cap bounds WRITE intents only. Read-tool audit rows (caller "read-tool", added
    // in M5 T-027 for the complete tool-call trail) must NOT consume the write budget, or a
    // read-heavy turn would spuriously trip the cap and demote legitimate grounded auto-posts to
    // confirm cards (council: Tamir MED). Count rows whose caller is not "read-tool" (NULL-caller
    // legacy rows still count as write intents).
    const [{ c: total }] = await db
      .select({ c: count() })
      .from(auditLog)
      .where(and(gte(auditLog.createdAt, since), or(ne(auditLog.caller, "read-tool"), isNull(auditLog.caller))));
    const destructive = isDestructive(opName);
    let dtotal = 0;
    if (destructive) {
      const [{ c }] = await db
        .select({ c: count() })
        .from(auditLog)
        .where(
          and(
            gte(auditLog.createdAt, since),
            inArray(auditLog.name, [...DESTRUCTIVE_OPS]),
          ),
        );
      dtotal = Number(c);
    }
    return capDecision(Number(total), dtotal, destructive);
  } catch {
    return !isDestructive(opName);
  }
}
