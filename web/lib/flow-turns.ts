// The server-authenticated operator-turn record (spec 009 M5 / D-052).
//
// Multi-turn grounding has one load-bearing security property: the numerals the
// auto-post verdict trusts must come from what the OPERATOR actually typed, not from
// anything a client can forge. The request carries a role-tagged transcript for parser
// context and resume, but that transcript is client-supplied and therefore untrusted for
// grounding. So the server keeps its OWN append-only record of each inbound operator
// message, keyed by (owner, flow_nonce), and grounding (lib/verdict.ts via
// lib/ops/stage.ts) runs only against this record. A forged operator turn in the request
// body is never written here, so it can never launder an ungrounded amount onto the auto
// path (AC10).
//
// Two server-side bounds keep the trusted corpus tight, so corpus integrity does not rest
// on the client honoring flow-close (council: Tamir/Winston/Marcus):
//   - `owner` binds the record to the authenticated operator. Reads and writes filter by
//     (owner, flow_nonce), so one session can never seed or read another's corpus even if
//     it reuses a known nonce.
//   - FLOW_TTL_MS bounds grounding to the RECENT active flow. An abandoned or client-pinned
//     nonce drops out of the corpus after the window, so a stale operator-typed numeral can
//     never complete a sale or ground a later auto-post (the BLOCKER Tamir found).
//
// It is deliberately lighter than a full conversation store (the dropped specs-001/002
// session table): operator utterances for ONE active flow only, never assistant turns.

import { and, asc, eq, gte } from "drizzle-orm";
import { db } from "@/lib/db";
import { operatorTurns } from "@/db/schema";

// The active-flow window. A flow stays groundable for this long after its last operator
// turn; beyond it, grounding treats the nonce as a fresh flow (nothing to complete, empty
// corpus). Ten minutes comfortably covers an "a que precio?" round-trip while killing the
// stale-completion vector.
export const FLOW_TTL_MS = 10 * 60 * 1000;

function isoNow(): string {
  return new Date().toISOString();
}

export interface OperatorTurn {
  text: string;
  createdAt: string;
}

// Append one operator turn to the server-authenticated record, server-side, from the real
// inbound message. Returns the new seq. Append-only: never updates a row. The seq is
// derived from the current max for (owner, flow_nonce); the unique (flow_nonce, seq) index
// makes a concurrent collision fail loudly rather than silently duplicate.
export async function appendOperatorTurn(owner: string, flowNonce: string, text: string): Promise<number> {
  const existing = await db
    .select({ seq: operatorTurns.seq })
    .from(operatorTurns)
    .where(and(eq(operatorTurns.owner, owner), eq(operatorTurns.flowNonce, flowNonce)));
  const seq = existing.length ? Math.max(...existing.map((r) => r.seq)) + 1 : 0;
  await db.insert(operatorTurns).values({ owner, flowNonce, seq, text, createdAt: isoNow() });
  return seq;
}

// Every operator turn recorded for (owner, flow) within the TTL window, oldest first.
// These are the ONLY turns grounding may read; assistant turns are never recorded, and a
// turn older than the window is excluded so a stale flow cannot ground a fresh write.
export async function operatorTurnsFor(owner: string, flowNonce: string): Promise<OperatorTurn[]> {
  if (!flowNonce) return [];
  const sinceIso = new Date(Date.now() - FLOW_TTL_MS).toISOString();
  const rows = await db
    .select({ text: operatorTurns.text, createdAt: operatorTurns.createdAt })
    .from(operatorTurns)
    .where(
      and(
        eq(operatorTurns.owner, owner),
        eq(operatorTurns.flowNonce, flowNonce),
        gte(operatorTurns.createdAt, sinceIso),
      ),
    )
    .orderBy(asc(operatorTurns.seq));
  return rows;
}

// The grounding corpus for a flow: the operator's own recorded turns (within the TTL)
// joined into one string the numeral/name grounding scans. This is what lib/verdict.ts
// grounds against — never the client transcript.
export async function groundingCorpusFor(owner: string, flowNonce: string): Promise<string> {
  const turns = await operatorTurnsFor(owner, flowNonce);
  return turns.map((t) => t.text).join("\n");
}
