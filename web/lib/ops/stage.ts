// Shared staging: re-derive resolution + grounded amounts + the server-side verdict
// for a proposed op, write only the pending_ops preview, append a staged audit row.
// Used by POST /api/ops/stage and by the chat route. The model never sets the verdict.
import { getOp } from "@/lib/ops/registry";
import type { RefCandidate } from "@/lib/ops/resolve-ref";
import * as pending from "@/lib/pending-ops";
import { computeVerdict, demoteOverTurnCap } from "@/lib/verdict";
import { withinCaps, appendAudit } from "@/lib/audit";

export type StageOutcome =
  | {
      ok: true;
      op_token: string;
      auto: boolean;
      requires_human_review: boolean;
      reasons: string[];
      preview: Record<string, unknown>;
      // The full-consequence line for a destructive/edit confirm card (spec 009 AC6), or
      // null for a write op whose preview the client summarizes from the args.
      consequence: string | null;
      product_name: string | null;
      candidate_count: number;
      operation_type: string;
      // Whether this op can be undone after commit (drives the chat's Deshacer affordance).
      // An irreversible op (price change, product register, cancel, deactivate) has no undo.
      reversible: boolean;
    }
  // Ambiguous reference (spec 009 AC5): a descriptor matched more than one row. Nothing is
  // staged; the caller renders a disambiguation picker and re-stages with the chosen id.
  // pending_args carries the non-id resolved args (e.g. the new price for UPDATE_PRICE) so
  // the picker re-stage does not lose them — a pick must not drop the thing being changed.
  | { ok: false; code: "ambiguous_reference"; message: string; candidates: RefCandidate[]; operation_type: string; id_field: string; pending_args: Record<string, unknown> }
  | { ok: false; code: string; message: string };

// Spanish article for a reference noun, for a grammatical not-found message. Masculine
// nouns ("gasto", "proveedor") take "un"; feminine ("venta", "entrada") take "una".
function articleFor(noun: string): string {
  return noun === "gasto" || noun === "proveedor" ? "un" : "una";
}

// Best-effort product reference text for a clean "not found" message.
function productRefOf(args: Record<string, unknown>): string | null {
  if (typeof args.productRef === "string" && args.productRef.trim()) return args.productRef.trim();
  const items = args.items as Array<{ productRef?: unknown }> | undefined;
  const first = items?.[0]?.productRef;
  if (typeof first === "string" && first.trim()) return first.trim();
  return null;
}

export async function stageOperation(input: {
  operationType: string;
  args?: Record<string, unknown>;
  utterance?: string;
  turnNonce?: string;
  // The server-authenticated grounding corpus for the active flow (spec 009 M5 / D-052).
  // When set, the verdict grounds numerals and the product name against the operator's own
  // recorded turns in this flow, not the single utterance. Omitted for a single-turn stage
  // (the direct /api/ops/stage path, the disambiguation re-stage) where the utterance is
  // the whole flow. Never carries the client transcript — the chat route builds it from
  // lib/flow-turns.ts, the server's own record.
  groundingCorpus?: string;
}): Promise<StageOutcome> {
  const operationType = (input.operationType ?? "").toUpperCase();
  const op = getOp(operationType);
  if (!op) return { ok: false, code: "unknown_operation", message: `Unknown operation ${operationType}` };

  const utterance = input.utterance ?? "";
  const resolved = await op.resolve(input.args ?? {});

  // Ambiguous reference (spec 009 AC5): a descriptor matched more than one row and the op
  // can disambiguate (it declares a refIdField). Stage nothing; hand the caller the
  // candidates so it renders a picker and re-stages with the server-resolved id.
  if (op.refIdField && resolved.candidateCount > 1 && resolved.candidates?.length) {
    return {
      ok: false,
      code: "ambiguous_reference",
      message: `Encontre ${resolved.candidates.length} coincidencias. Cual?`,
      candidates: resolved.candidates,
      operation_type: operationType,
      id_field: op.refIdField,
      // Everything the op already resolved EXCEPT the id the pick supplies (the id field
      // is stripped so the chosen candidate's id wins). For UPDATE_PRICE this carries
      // unitPriceCents; for the cancels it is empty.
      pending_args: Object.fromEntries(Object.entries(resolved.stagedArgs).filter(([k]) => k !== op.refIdField)),
    };
  }

  // Nothing resolved. A product-bound op (sale/stock/price/deactivate) returns a
  // product_not_found so the chat can offer a create-then-act heal; a reference op
  // (cancel sale/expense/stock) returns a clean reference_not_found. Without this guard
  // the op staged a confirmable card and the commit then failed with a raw DB error.
  if (resolved.candidateCount === 0) {
    if (op.refNoun && op.refNoun !== "producto") {
      return { ok: false, code: "reference_not_found", message: `No encontre ${articleFor(op.refNoun)} ${op.refNoun} que coincida. Deci cual con mas detalle (por ejemplo "la ultima" o el nombre).` };
    }
    const ref = productRefOf(input.args ?? {});
    return {
      ok: false,
      code: "product_not_found",
      message: ref
        ? `No encontre un producto que coincida con "${ref}". Registralo primero (podes decir "nuevo producto ${ref}") o revisa el nombre.`
        : "No pude resolver el producto de esa operacion. Registralo primero o revisa el nombre.",
    };
  }

  const opToken = crypto.randomUUID();
  const turnNonce = input.turnNonce ?? crypto.randomUUID();
  await pending.stage({
    opToken,
    operationType,
    args: resolved.stagedArgs,
    utterance,
    productName: resolved.productName,
    candidateCount: resolved.candidateCount,
    turnNonce,
  });
  const caps = await withinCaps(operationType);
  const baseVerdict = computeVerdict({
    operationType,
    utterance,
    groundedAmounts: resolved.groundedAmounts,
    productName: resolved.productName,
    candidateCount: resolved.candidateCount,
    withinCaps: caps,
    irreversible: op.irreversible,
    requiresHumanReview: op.requiresHumanReview,
    groundingCorpus: input.groundingCorpus,
  });
  // Per-turn auto-post cap (spec 010 M5, T-023, AC-T6): bound how many reversible writes a single
  // grounded turn can auto-post. The current row is already staged with auto=NULL, so the count is
  // strictly the prior auto writes of this turn; at or above the cap, demote to a confirm card.
  const priorAuto = await pending.countAutoForTurn(turnNonce);
  const verdict = demoteOverTurnCap(baseVerdict, priorAuto);
  await pending.setVerdict(opToken, verdict);
  await appendAudit({ name: operationType, args: resolved.stagedArgs, caller: "stage", opToken, outcome: "staged" });

  return {
    ok: true,
    op_token: opToken,
    auto: verdict.auto,
    requires_human_review: verdict.requiresHumanReview,
    reasons: verdict.reasons,
    preview: resolved.stagedArgs,
    consequence: resolved.preview ?? null,
    product_name: resolved.productName,
    candidate_count: resolved.candidateCount,
    operation_type: operationType,
    reversible: !op.irreversible,
  };
}
