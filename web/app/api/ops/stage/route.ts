// POST /api/ops/stage — stage a validated op and compute the server-side verdict.
// Writes NO business row (only the pending_ops preview). The parser's proposal is
// re-derived here; the model never sets the auto flag. (spec 008 AC5/AC6.)
import { auth } from "@/auth";
import { ok, fail, requireDb } from "@/lib/http";
import { stageOperation } from "@/lib/ops/stage";

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
  try {
    const r = await stageOperation({
      operationType: body.operationType ?? "",
      args: body.args,
      utterance: body.utterance,
      turnNonce: body.turnNonce,
    });
    if (!r.ok) return fail(r.code, r.message);
    const { ok: _ok, ...data } = r;
    return ok(data);
  } catch (e) {
    return fail("stage_failed", (e as Error).message, 422);
  }
}
