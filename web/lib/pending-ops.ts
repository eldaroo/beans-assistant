// Two-phase write staging. Ported from backend/repositories/pending_ops_repository.py
// (spec 007 D-038/D-043) onto the single-business pending_ops table.
//
// A write never commits. It stages a validated preview here under an op_token; the
// non-model /confirm route is the only thing that commits it. The row is DB-backed so
// it survives a restart and is reachable from any serverless invocation.
//
// Lifecycle: staged PENDING (auto NULL = verdict not yet computed) -> app computes the
// verdict and sets auto/requires_human_review -> /confirm claims PENDING->COMMITTING
// atomically (single winner) then COMMITTING->COMMITTED once -> Undo path flips
// COMMITTED->CANCELLING->CANCELLED. Every transition is one conditional UPDATE whose
// row count names the single winner, which is exactly what neon-http delivers per query.

import { and, asc, count, eq, ne } from "drizzle-orm";
import { db } from "@/lib/db";
import { pendingOps } from "@/db/schema";
import type { Verdict } from "@/lib/verdict";

function isoNow(): string {
  return new Date().toISOString();
}

export interface PendingOp {
  opToken: string;
  operationType: string;
  args: unknown;
  utterance: string | null;
  productName: string | null;
  candidateCount: number | null;
  turnNonce: string | null;
  auto: number | null;
  requiresHumanReview: number | null;
  status: string;
  commitResult: unknown;
  reasons: unknown;
  createdAt: string;
  committedAt: string | null;
}

function hydrate(row: typeof pendingOps.$inferSelect): PendingOp {
  const parse = (v: string | null): unknown => {
    if (!v) return v;
    try {
      return JSON.parse(v);
    } catch {
      return v;
    }
  };
  return {
    ...row,
    args: parse(row.args),
    commitResult: parse(row.commitResult),
    reasons: parse(row.reasons),
  };
}

// Insert a PENDING op with the verdict not yet computed (auto NULL). Returns created_at.
// turn_nonce identifies the agent turn that staged this op, so the app correlates a
// staged write to THIS turn by identity, not by wall-clock.
export async function stage(params: {
  opToken: string;
  operationType: string;
  args: unknown;
  utterance?: string | null;
  productName?: string | null;
  candidateCount?: number | null;
  turnNonce?: string | null;
}): Promise<string> {
  const createdAt = isoNow();
  await db.insert(pendingOps).values({
    opToken: params.opToken,
    operationType: params.operationType,
    args: JSON.stringify(params.args),
    utterance: params.utterance ?? null,
    productName: params.productName ?? null,
    candidateCount: params.candidateCount ?? null,
    turnNonce: params.turnNonce ?? null,
    auto: null,
    requiresHumanReview: null,
    status: "PENDING",
    createdAt,
  });
  return createdAt;
}

export async function setVerdict(opToken: string, verdict: Verdict): Promise<void> {
  await db
    .update(pendingOps)
    .set({
      auto: verdict.auto ? 1 : 0,
      requiresHumanReview: verdict.requiresHumanReview ? 1 : 0,
      reasons: JSON.stringify(verdict.reasons),
    })
    .where(eq(pendingOps.opToken, opToken));
}

export async function get(opToken: string): Promise<PendingOp | null> {
  const rows = await db
    .select()
    .from(pendingOps)
    .where(eq(pendingOps.opToken, opToken))
    .limit(1);
  return rows.length ? hydrate(rows[0]) : null;
}

// Atomically transition PENDING -> COMMITTING. Returns true for the single winner;
// two concurrent confirms of one op_token can never both post.
export async function claim(opToken: string): Promise<boolean> {
  const won = await db
    .update(pendingOps)
    .set({ status: "COMMITTING" })
    .where(and(eq(pendingOps.opToken, opToken), eq(pendingOps.status, "PENDING")))
    .returning({ opToken: pendingOps.opToken });
  return won.length > 0;
}

// Revert COMMITTING -> PENDING when the commit is rejected by a guard, so a later
// retry (e.g. after stock is added) can claim and commit it again.
export async function unclaim(opToken: string): Promise<void> {
  await db
    .update(pendingOps)
    .set({ status: "PENDING" })
    .where(and(eq(pendingOps.opToken, opToken), eq(pendingOps.status, "COMMITTING")));
}

// Finalize COMMITTING -> COMMITTED, recording the commit result. Returns true on the
// transition (the claimer).
export async function markCommitted(
  opToken: string,
  commitResult: unknown,
): Promise<boolean> {
  const won = await db
    .update(pendingOps)
    .set({
      status: "COMMITTED",
      commitResult: JSON.stringify(commitResult),
      committedAt: isoNow(),
    })
    .where(and(eq(pendingOps.opToken, opToken), eq(pendingOps.status, "COMMITTING")))
    .returning({ opToken: pendingOps.opToken });
  return won.length > 0;
}

// Atomically transition COMMITTED -> CANCELLING for the Undo path. Returns true for
// the single winner, so a double Undo tap compensates at most once.
export async function claimCancel(opToken: string): Promise<boolean> {
  const won = await db
    .update(pendingOps)
    .set({ status: "CANCELLING" })
    .where(and(eq(pendingOps.opToken, opToken), eq(pendingOps.status, "COMMITTED")))
    .returning({ opToken: pendingOps.opToken });
  return won.length > 0;
}

export async function finalizeCancelled(opToken: string): Promise<void> {
  await db
    .update(pendingOps)
    .set({ status: "CANCELLED" })
    .where(and(eq(pendingOps.opToken, opToken), eq(pendingOps.status, "CANCELLING")));
}

// Revert CANCELLING -> COMMITTED if the compensator failed, so Undo can be retried.
export async function revertCancel(opToken: string): Promise<void> {
  await db
    .update(pendingOps)
    .set({ status: "COMMITTED" })
    .where(and(eq(pendingOps.opToken, opToken), eq(pendingOps.status, "CANCELLING")));
}

// Every op this turn staged that is still PENDING (not yet committed or cancelled),
// correlated by the turn nonce, oldest first (spec 010 M3, T-016, D-062). This is how the
// chat route recovers the op_tokens the box staged inside the gateway tool loop: the token
// never crosses the gateway or the model (callPreview strips it), so the route reads the
// staged ops back from Neon by the nonce IT minted and injected out of band, then renders
// the confirm card / auto-post in order. A list so a compound turn (one message that stages
// a sale AND an expense) surfaces every staged write.
//
// The ops come back WITH their server-computed verdict already set: stageOperation grounds
// and computes the verdict at the internal preview endpoint (D-061), then stages the op, so a
// PENDING row for the turn already carries auto/requires_human_review/reasons. The readback
// filters only on (turn, PENDING) — an op the route already rendered and the owner committed
// leaves PENDING, so it never re-renders; a still-PENDING op is exactly the unrendered set.
// How many AUTO writes this turn has already staged (spec 010 M5, T-023). Counts auto=1 rows
// under the turn nonce that are not CANCELLED, so a demoted/undone write does not count against
// the cap. The current row is staged with auto=NULL before its verdict is set, so it is never
// counted here — the count is strictly the PRIOR auto writes of this turn. Empty nonce -> 0.
export async function countAutoForTurn(turnNonce: string): Promise<number> {
  if (!turnNonce) return 0;
  const [{ c }] = await db
    .select({ c: count() })
    .from(pendingOps)
    .where(
      and(
        eq(pendingOps.turnNonce, turnNonce),
        eq(pendingOps.auto, 1),
        ne(pendingOps.status, "CANCELLED"),
      ),
    );
  return Number(c);
}

export async function verdictPendingForTurn(turnNonce: string): Promise<PendingOp[]> {
  if (!turnNonce) return [];
  const rows = await db
    .select()
    .from(pendingOps)
    .where(
      and(
        eq(pendingOps.turnNonce, turnNonce),
        eq(pendingOps.status, "PENDING"),
      ),
    )
    // Deterministic tiebreaker (council: Winston NIT): batch rows staged in a tight loop can share
    // a millisecond createdAt, and there is no monotonic id column (the PK is the random opToken).
    // Ordering by opToken as the tiebreaker makes the read STABLE across re-renders (the independent
    // batch cards keep one consistent order), which is the enforceable form of the ordering contract.
    .orderBy(asc(pendingOps.createdAt), asc(pendingOps.opToken));
  return rows.map(hydrate);
}
