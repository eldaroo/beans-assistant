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
    }
  | { ok: false; code: string; message: string };

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
  };
}
