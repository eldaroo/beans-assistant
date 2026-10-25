// Shared staging: re-derive resolution + grounded amounts + the server-side verdict
// for a proposed op, write only the pending_ops preview, append a staged audit row.
// Used by POST /api/ops/stage and by the chat route. The model never sets the verdict.
import { getOp } from "@/lib/ops/registry";
import * as pending from "@/lib/pending-ops";
import { computeVerdict } from "@/lib/verdict";
import { withinCaps, appendAudit } from "@/lib/audit";

export type StageOutcome =
  | {
      ok: true;
      op_token: string;
      auto: boolean;
      requires_human_review: boolean;
      reasons: string[];
      preview: Record<string, unknown>;
      product_name: string | null;
      candidate_count: number;
      operation_type: string;
      // Whether this op can be undone after commit (drives the chat's Deshacer affordance).
      // An irreversible op (price change, product register, cancel, deactivate) has no undo.
      reversible: boolean;
    }
  | { ok: false; code: string; message: string };

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
}): Promise<StageOutcome> {
  const operationType = (input.operationType ?? "").toUpperCase();
  const op = getOp(operationType);
  if (!op) return { ok: false, code: "unknown_operation", message: `Unknown operation ${operationType}` };

  const utterance = input.utterance ?? "";
  const resolved = await op.resolve(input.args ?? {});

  // Guard a product-bound op whose reference did not resolve to any active product.
  // Only product-looking-up ops (sale/stock/price/deactivate) can return 0 here;
  // expense and product-registration hardcode a count of 1. Without this guard the
  // op staged a confirmable card and the commit then failed with a raw DB error
  // (product_id DEFAULT -> NOT NULL/FK violation). Fail cleanly and actionably.
  if (resolved.candidateCount === 0) {
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
  const verdict = computeVerdict({
    operationType,
    utterance,
    groundedAmounts: resolved.groundedAmounts,
    productName: resolved.productName,
    candidateCount: resolved.candidateCount,
    withinCaps: caps,
    irreversible: op.irreversible,
  });
  await pending.setVerdict(opToken, verdict);
  await appendAudit({ name: operationType, args: resolved.stagedArgs, caller: "stage", opToken, outcome: "staged" });

  return {
    ok: true,
    op_token: opToken,
    auto: verdict.auto,
    requires_human_review: verdict.requiresHumanReview,
    reasons: verdict.reasons,
    preview: resolved.stagedArgs,
    product_name: resolved.productName,
    candidate_count: resolved.candidateCount,
    operation_type: operationType,
    reversible: !op.irreversible,
  };
}
