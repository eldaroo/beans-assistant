// The app<->parser contract. The parser (remote on Nomad, or the local fallback)
// turns operator text into a PROPOSAL; it never executes anything. The app
// re-derives the verdict and is the only thing that commits.
//
// Spec 009 widens this contract two ways, both on top of the unchanged spine:
//   1. An action proposal is an ORDERED LIST of steps (D-047). Each step stays its
//      own unit of commit: one op_token, one verdict, one /api/ops/confirm. There is
//      no cross-step transaction. The common case is a single step; a product-not-found
//      heals into a two-step compound (REGISTER_PRODUCT then the sale or stock).
//   2. A proposal is a DISCRIMINATED UNION with a read-only QUERY kind (D-049). A query
//      is dispatched off the write path to the read registry: no stage, no verdict, no
//      commit, no undo. The `kind` field discriminates.

// One parsed operation: the parser proposes a type and raw args; the app re-derives
// everything load-bearing (resolution, grounded amounts, verdict) at stage time.
export interface ParsedOp {
  operationType: string;
  args: Record<string, unknown>;
}

// A write proposal: an ordered list of steps, each its own commit unit.
export interface ActionProposal {
  kind: "action";
  steps: ParsedOp[];
  utterance: string;
  source: "remote" | "fallback";
  note?: string;
}

// A read proposal: dispatched to the read registry, never staged or committed.
export interface QueryProposal {
  kind: "query";
  queryId: string;
  args: Record<string, unknown>;
  utterance: string;
  source: "remote" | "fallback";
  note?: string;
}

export type Proposal = ActionProposal | QueryProposal;

// Narrowing helpers so call sites branch on the discriminant, never on a cast.
export function isQuery(p: Proposal): p is QueryProposal {
  return p.kind === "query";
}
export function isAction(p: Proposal): p is ActionProposal {
  return p.kind === "action";
}

// Build a single-step action proposal from one parsed op. The remote parser and the
// local fallback both emit one op today; this wraps it into the ordered-steps shape
// without changing the parser wire contract.
export function actionOf(
  op: ParsedOp,
  utterance: string,
  source: "remote" | "fallback",
  note?: string,
): ActionProposal {
  return { kind: "action", steps: [op], utterance, source, note };
}
