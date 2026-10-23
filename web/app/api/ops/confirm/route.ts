// POST /api/ops/confirm — the single, non-model commit path. Claims the pending op
// (single winner), runs the domain commit, records the result. Idempotent: a second
// confirm returns the committed values read back from the store. (spec 008 AC5.)
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
  if (po.status === "COMMITTED") return ok({ committed: true, idempotent: true, result: po.commitResult });

  const op = getOp(po.operationType);
  if (!op) return fail("unknown_operation", `Unknown operation ${po.operationType}`);

  const won = await pending.claim(opToken);
  if (!won) {
    const re = await pending.get(opToken);
    if (re?.status === "COMMITTED") return ok({ committed: true, idempotent: true, result: re.commitResult });
    return fail("not_committable", `op is in state ${re?.status ?? "unknown"}`, 409);
  }

  try {
    const result = await op.commit(po.args as Record<string, unknown>);
    await pending.markCommitted(opToken, result);
    await appendAudit({ name: po.operationType, args: po.args, caller: "confirm", opToken, outcome: "committed" });
    return ok({ committed: true, result });
  } catch (e) {
    await pending.unclaim(opToken);
    await appendAudit({ name: po.operationType, caller: "confirm", opToken, outcome: "error" });
    return fail("commit_failed", (e as Error).message, 422);
  }
}
