// POST /api/ops/undo — the loud-Undo compensation for a committed reversible op.
// Claims COMMITTED->CANCELLING (single winner, so a double tap compensates at most
// once), runs the domain undo, finalizes. (spec 008: reversible posts, loud Undo.)
import { auth } from "@/auth";
import { ok, fail, requireDb } from "@/lib/http";
import { getOp } from "@/lib/ops/registry";
import * as pending from "@/lib/pending-ops";
import { appendAudit } from "@/lib/audit";

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user) return fail("unauthorized", "Sign in required", 401);
  const dbErr = requireDb();
  if (dbErr) return dbErr;

  let body: { op_token?: string };
  try {
    body = await req.json();
  } catch {
    return fail("bad_json", "Request body must be JSON");
  }
  const opToken = body.op_token;
  if (!opToken) return fail("missing_op_token", "op_token is required");

  const po = await pending.get(opToken);
  if (!po) return fail("unknown_op", "No such pending op", 404);
  if (po.status === "CANCELLED") return ok({ undone: true, idempotent: true });
  if (po.status !== "COMMITTED") return fail("not_undoable", `op is in state ${po.status}`, 409);

  const op = getOp(po.operationType);
  if (!op?.undo) return fail("not_reversible", `${po.operationType} has no undo`, 422);

  const won = await pending.claimCancel(opToken);
  if (!won) {
    const re = await pending.get(opToken);
    if (re?.status === "CANCELLED") return ok({ undone: true, idempotent: true });
    return fail("not_undoable", `op is in state ${re?.status ?? "unknown"}`, 409);
  }

  try {
    await op.undo(po.commitResult as Record<string, unknown>);
    await pending.finalizeCancelled(opToken);
    await appendAudit({ name: `undo_${po.operationType}`, caller: "undo", opToken, outcome: "cancelled" });
    return ok({ undone: true });
  } catch (e) {
    await pending.revertCancel(opToken);
    return fail("undo_failed", (e as Error).message, 422);
  }
}
