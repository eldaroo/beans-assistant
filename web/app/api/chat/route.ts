// POST /api/chat — the Timonel chat turn (spec 009). Two paths off one entry:
//
//   1. QUERY (read-only): a question is dispatched to the read registry and answered in
//      place. It never stages, verdicts, commits, or reaches /api/ops/confirm. (AC8/AC9)
//   2. ACTION (write): the text parses into an ordered-steps proposal. The first step is
//      staged (the server re-derives the verdict). A product-not-found on a stock or sale
//      heals into a two-step COMPOUND create-then-act instead of a dead-end error. (AC1)
//
// The chat never commits: /api/ops/confirm is the only commit path, one op_token at a
// time. The step stays the unit of commit; there is no cross-step transaction. (AC3)
import { auth } from "@/auth";
import { ok, fail, requireDb } from "@/lib/http";
import { dispatchQuery } from "@/lib/ops/query";
import { parseMessage } from "@/lib/parse/client";
import { isQuery } from "@/lib/parse/types";
import { stageOperation } from "@/lib/ops/stage";
import { isCompoundableAct, productRefOfStep, stripModelIds } from "@/lib/ops/compound";

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
    // 1. Read-only query, dispatched before the write path. Writes nothing.
    const q = await dispatchQuery(message);
    if (q) return ok({ kind: "answer", reply: q.reply, query_id: q.queryId });

    // 2. Parse into an action proposal (ordered steps). Queries are handled above, so a
    //    parsed proposal is always an action; the guard keeps the discriminant honest.
    const proposal = await parseMessage(message);
    if (!proposal) {
      return ok({
        kind: "unparsed",
        reply: "No pude interpretar eso como una operacion. Proba, por ejemplo: 'vendi 2 medias a 300', 'gaste 500 en envio', 'llegaron 10 termos', o preguntame 'cuanto vendi hoy'.",
      });
    }
    // Forward-compat: the QueryProposal arm of the union exists for a future parser that
    // emits reads directly. Today reads are caught by the deterministic dispatchQuery above
    // (pre-parse), so parseMessage only ever returns an action. This guard narrows the type
    // and will route a parser-emitted query the day one exists; it is not reached in C1.
    if (isQuery(proposal)) {
      return ok({ kind: "unparsed", reply: "No encontre ese dato." });
    }

    const turnNonce = body.turnNonce ?? crypto.randomUUID();
    // C1 stages the first step only. The parser emits a single-step proposal; multi-step
    // (attribute expansion) is M5, which will iterate proposal.steps. Strip EVERY model-
    // supplied id (product + sale/expense/stock reference) so the parser proposes
    // descriptors only (D-050 / AC4); the server mints and threads ids itself on the
    // compound re-stage or the disambiguation pick.
    const step = stripModelIds(proposal.steps[0]);

    // 3. Stage the first step. The app re-derives the verdict; nothing is written yet.
    const staged = await stageOperation({
      operationType: step.operationType,
      args: step.args,
      utterance: proposal.utterance,
      turnNonce,
    });

    if (!staged.ok) {
      // Disambiguation (AC5): a descriptor matched more than one row. Return a picker;
      // each option carries the server-resolved id, and selecting one re-enters staging
      // with that id through /api/ops/stage (not the parser path, so the id is trusted).
      if (staged.code === "ambiguous_reference" && "candidates" in staged) {
        return ok({
          kind: "disambiguation",
          operation_type: staged.operation_type,
          id_field: staged.id_field,
          candidates: staged.candidates,
          // Carry the non-id resolved args (e.g. the new price) so the pick re-stage keeps
          // the thing being changed; a pick that dropped it would commit a no-op.
          pending_args: staged.pending_args,
          utterance: proposal.utterance,
          turn_nonce: turnNonce,
        });
      }
      // Compound heal (AC1): a product-not-found on a stock or sale becomes a two-step
      // create-then-act. Step 1 mints a minimal product from the name; step 2 is the
      // original act, threaded to the created id at confirm time (client-driven, in
      // order). The step stays the commit unit (AC3): no cross-step transaction.
      if (staged.code === "product_not_found" && isCompoundableAct(step.operationType)) {
        const ref = productRefOfStep(step);
        if (ref) {
          const reg = await stageOperation({
            operationType: "REGISTER_PRODUCT",
            args: { name: ref },
            utterance: proposal.utterance,
            turnNonce,
          });
          if (reg.ok) {
            return ok({
              kind: "compound",
              turn_nonce: turnNonce,
              product_name: ref,
              source: proposal.source,
              steps: [
                { step: 1, role: "register", op_token: reg.op_token, operation_type: reg.operation_type, preview: reg.preview },
                { step: 2, role: "act", operation_type: step.operationType, pending_args: step.args, utterance: proposal.utterance },
              ],
            });
          }
        }
      }
      return fail(staged.code, staged.message);
    }

    return ok({
      kind: "proposal",
      op_token: staged.op_token,
      auto: staged.auto,
      requires_human_review: staged.requires_human_review,
      reasons: staged.reasons,
      preview: staged.preview,
      consequence: staged.consequence,
      product_name: staged.product_name,
      operation_type: staged.operation_type,
      reversible: staged.reversible,
      source: proposal.source,
    });
  } catch (e) {
    return fail("chat_failed", (e as Error).message, 422);
  }
}
