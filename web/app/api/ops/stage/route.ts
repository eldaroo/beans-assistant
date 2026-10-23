// POST /api/ops/stage — stage a validated op and compute the server-side verdict.
// Writes NO business row (only the pending_ops preview). The parser's proposal is
// re-derived here; the model never sets the auto flag. (spec 008 AC5/AC6.)
import { auth } from "@/auth";
import { ok, fail, requireDb } from "@/lib/http";
import { getOp } from "@/lib/ops/registry";
import * as pending from "@/lib/pending-ops";
import { computeVerdict } from "@/lib/verdict";
import { withinCaps, appendAudit } from "@/lib/audit";

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user) return fail("unauthorized", "Sign in required", 401);
  const dbErr = requireDb();
  if (dbErr) return dbErr;

  let body: { operationType?: string; args?: Record<string, unknown>; utterance?: string; turnNonce?: string };
  try {
    body = await req.json();
  } catch {
    return fail("bad_json", "Request body must be JSON");
  }
  const operationType = body.operationType ?? "";
  const op = getOp(operationType);
  if (!op) return fail("unknown_operation", `Unknown operation ${operationType}`);

  const utterance = body.utterance ?? "";
  try {
    const resolved = await op.resolve(body.args ?? {});
    const opToken = crypto.randomUUID();
    const turnNonce = body.turnNonce ?? crypto.randomUUID();
    await pending.stage({
      opToken,
      operationType: operationType.toUpperCase(),
      args: resolved.stagedArgs,
      utterance,
      productName: resolved.productName,
      candidateCount: resolved.candidateCount,
      turnNonce,
    });
    const caps = await withinCaps(operationType.toUpperCase());
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
    await appendAudit({ name: operationType.toUpperCase(), args: resolved.stagedArgs, caller: "stage", opToken, outcome: "staged" });
    return ok({
      op_token: opToken,
      auto: verdict.auto,
      requires_human_review: verdict.requiresHumanReview,
      reasons: verdict.reasons,
      preview: resolved.stagedArgs,
      product_name: resolved.productName,
      candidate_count: resolved.candidateCount,
    });
  } catch (e) {
    return fail("stage_failed", (e as Error).message, 422);
  }
}
