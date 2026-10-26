// POST /api/internal/ops/preview/[tool] — the internal write-PREVIEW endpoint family (spec 010
// M3, T-013/T-014/T-016; D-059/D-060/D-061/D-062). The beans-ai box's MCP write-preview tools
// reach it over the internal-ops wire: service token (internalGuard), tenant pinned and
// allowlisted out of band. It stages a validated preview via stageOperation and returns it WITH
// the op_token; the MCP's callPreview strips op_token before anything reaches the model (D-062).
// It commits no row. The true commit-boundary property (AC4): the MODEL never receives the
// op_token (callPreview strips it), and the only commit path (/api/ops/confirm) is session-only
// and rejects the service token. The owner's own browser commits this op_token after the route
// reads it back; the box and the model never hold a handle that could commit.
//
// THE GROUNDING KEYSTONE (D-061, AC5). The verdict grounds the staged numerals against the
// server-authenticated operator_turns record (groundingCorpusFor(owner, flowNonce)), read from
// the OUT-OF-BAND owner + flow nonce the gateway threaded, NEVER from the model's tool args. A
// model-invented numeral present in the args but absent from the operator's own words fails
// grounding -> auto:false -> confirm card. The arg mapping (lib/internal/preview-map) is pure,
// so no tool arg can leak into the grounding source. If the box did not thread owner/flow
// (empty), the corpus is empty and grounding fails closed: an ungrounded write never auto-posts.
import { NextResponse } from "next/server";
import { internalGuard } from "@/lib/internal-auth";
import { fail, requireDb } from "@/lib/http";
import { mapPreviewTool } from "@/lib/internal/preview-map";
import { stageOperation } from "@/lib/ops/stage";
import { operatorTurnsFor } from "@/lib/flow-turns";

export const runtime = "nodejs";

export async function POST(req: Request, ctx: { params: Promise<{ tool: string }> }) {
  const g = internalGuard(req.headers);
  if (!g.ok) return fail(g.code, g.message, g.status);
  const dbErr = requireDb();
  if (dbErr) return dbErr;

  const { tool } = await ctx.params;

  // The out-of-band facts the gateway threaded into the box's MCP env; NONE is a model tool arg
  // (D-061). owner + flowNonce key the grounding record; turnNonce stamps the staged op so the
  // route reads it back by the nonce IT minted (D-062). The model never sees any of them.
  const owner = (req.headers.get("x-beans-owner") ?? "").trim();
  const flowNonce = (req.headers.get("x-beans-flow") ?? "").trim();
  const turnNonce = (req.headers.get("x-beans-turn") ?? "").trim() || undefined;

  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return fail("bad_json", "Request body must be JSON");
  }

  const mapped = mapPreviewTool(tool, body ?? {});
  if (!mapped.ok) return fail(mapped.code, mapped.message, 400);

  // Build the grounding corpus + current utterance from the operator's OWN recorded turns, never
  // the tool args. The current turn (the latest recorded operator message) is the utterance the
  // bare-confirmation guard reads; the full flow record is the corpus the numeral/name grounding
  // scans. Empty owner/flow -> empty corpus -> grounding fails -> confirm card (fail safe).
  const turns = owner && flowNonce ? await operatorTurnsFor(owner, flowNonce) : [];
  const groundingCorpus = turns.map((t) => t.text).join("\n");
  const utterance = turns.length ? turns[turns.length - 1].text : "";

  // A batch tool (register_products_batch, M5 T-022) stages several ops under the SAME turn
  // nonce; the chat route's verdictPendingForTurn readback then renders one confirm card per
  // product in order. Every op is confirm-only (REGISTER_PRODUCT is irreversible), so a batch
  // can never auto-post. No op_token is returned (the route reads them back by the turn nonce);
  // the model gets only a count of what was prepared, to relay to the owner.
  if ("batch" in mapped) {
    try {
      const results = [];
      for (const inp of mapped.batch) {
        results.push(await stageOperation({ operationType: inp.operationType, args: inp.args, utterance, turnNonce, groundingCorpus }));
      }
      const staged = results.filter((r) => r.ok) as Extract<Awaited<ReturnType<typeof stageOperation>>, { ok: true }>[];
      const names = staged.map((r) => r.product_name).filter(Boolean);
      return NextResponse.json({
        ok: true,
        batch: true,
        staged_count: staged.length,
        requested_count: mapped.batch.length,
        products: names,
        // Confirm-only by construction; surfaced so the model tells the owner it needs confirmation.
        requires_human_review: true,
      });
    } catch (e) {
      console.error(`internal preview batch failed:`, (e as Error).message);
      return fail("preview_failed", "No pude preparar esas operaciones", 500);
    }
  }

  try {
    const r = await stageOperation({
      operationType: mapped.input.operationType,
      args: mapped.input.args,
      utterance, // the operator's own current turn, NOT the tool args
      turnNonce,
      groundingCorpus, // the operator's own flow record, NOT the tool args
    });
    if (!r.ok) {
      if (r.code === "ambiguous_reference" && "candidates" in r) {
        // A descriptor matched many rows: tell the model it was ambiguous and stage nothing.
        // The owner disambiguates in the command center; the box just surfaces the ambiguity.
        return NextResponse.json({
          ok: true,
          clarify: "ambiguous",
          message: r.message,
          candidate_count: r.candidates.length,
          operation_type: r.operation_type,
        });
      }
      // product_not_found / reference_not_found / unknown_operation: the model reads error.message
      // and tells the owner. The message is generic (no SQL/schema), set by stageOperation.
      return fail(r.code, r.message);
    }
    // op_token is included so the ROUTE can read it back by turnNonce (D-062); the MCP's
    // callPreview strips op_token before the model ever sees the result. Nothing here commits.
    return NextResponse.json({
      ok: true,
      op_token: r.op_token,
      operation_type: r.operation_type,
      product_name: r.product_name,
      preview: r.preview,
      consequence: r.consequence,
      auto: r.auto,
      reversible: r.reversible,
      requires_human_review: r.requires_human_review,
    });
  } catch (e) {
    // The error.message is lifted into model-visible tool output by the MCP, so return a generic
    // message and log the raw cause server-side only (Tamir, council M1/M2).
    console.error(`internal preview ${tool} failed:`, (e as Error).message);
    return fail("preview_failed", "No pude preparar esa operacion", 500);
  }
}
