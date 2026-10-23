// POST /api/chat — the Timonel chat turn. A read-only scenario question is answered
// in place (no write). Otherwise the text is parsed into a proposal and STAGED (the
// server computes the verdict); the reply tells the client to auto-post or show a
// confirm card. The chat never commits: /api/ops/confirm is the only commit path.
import { auth } from "@/auth";
import { ok, fail, requireDb } from "@/lib/http";
import { handleScenario } from "@/lib/domains/cost-scenario";
import { parseMessage } from "@/lib/parse/client";
import { stageOperation } from "@/lib/ops/stage";

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user) return fail("unauthorized", "Sign in required", 401);
  const dbErr = requireDb();
  if (dbErr) return dbErr;

  let body: { message?: string; turnNonce?: string };
  try {
    body = await req.json();
  } catch {
    return fail("bad_json", "Request body must be JSON");
  }
  const message = (body.message ?? "").trim();
  if (!message) return fail("empty_message", "El mensaje esta vacio");

  try {
    // 1. Read-only cost scenario, answered in place (writes nothing).
    const scenario = await handleScenario(message);
    if (scenario) return ok({ kind: "answer", reply: scenario });

    // 2. Parse into a proposal (remote parser or local fallback).
    const proposal = await parseMessage(message);
    if (!proposal) {
      return ok({
        kind: "unparsed",
        reply: "No pude interpretar eso como una operacion. Probá, por ejemplo: 'vendi 2 medias a 300', 'gaste 500 en envio', 'llegaron 10 termos'.",
      });
    }

    // 3. Stage it: the app re-derives the verdict. Nothing is written yet.
    const staged = await stageOperation({
      operationType: proposal.operationType,
      args: proposal.args,
      utterance: proposal.utterance,
      turnNonce: body.turnNonce,
    });
    if (!staged.ok) return fail(staged.code, staged.message);

    return ok({
      kind: "proposal",
      op_token: staged.op_token,
      auto: staged.auto,
      requires_human_review: staged.requires_human_review,
      reasons: staged.reasons,
      preview: staged.preview,
      product_name: staged.product_name,
      operation_type: staged.operation_type,
      source: proposal.source,
    });
  } catch (e) {
    return fail("chat_failed", (e as Error).message, 422);
  }
}
