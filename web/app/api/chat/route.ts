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
//
// Spec 009 M5 adds multi-turn context (AC10/AC11). A flow spans turns: "vendi 40 stanleys"
// (no price) -> the app asks "a que precio?" -> "32" completes the sale. The grounding that
// decides auto-post runs against a SERVER-AUTHENTICATED record of the operator's own turns
// in the active flow (lib/flow-turns.ts), never the client-supplied transcript — so a
// forged turn in the request body cannot launder an ungrounded amount onto the auto path.
// The request may carry a bounded role-tagged transcript for resume context; it is NEVER
// read for grounding.
import { auth } from "@/auth";
import { ok, fail, requireDb } from "@/lib/http";
import { dispatchQuery } from "@/lib/ops/query";
import { parseMessage } from "@/lib/parse/client";
import { fallbackParse } from "@/lib/parse/fallback";
import { isQuery, isAction, actionOf, type ActionProposal } from "@/lib/parse/types";
import { stageOperation } from "@/lib/ops/stage";
import { isCompoundableAct, productRefOfStep, stripModelIds } from "@/lib/ops/compound";
import { appendOperatorTurn, groundingCorpusFor, operatorTurnsFor } from "@/lib/flow-turns";
import { priceAnswer, needsSalePrice, applySalePrice } from "@/lib/flow";
import { resolveActiveProduct } from "@/lib/domains/products";
import { gatewayConfigured, agentTimeoutMs } from "@/lib/gateway/client";
import { gatewayAnswer } from "@/lib/gateway/brain";

// The synchronous agent budget sits under this route cap (spec 010 T-006, D-063): the gateway
// per-call timeout (agentTimeoutMs, default 45s) must be < maxDuration so the route always runs
// its own parser fallback rather than being killed by the platform. If live latency in M3
// (A-Q21) exceeds this, the call goes async; for now it is synchronous with the fallback.
export const maxDuration = 60;

type SaleItem = { productId?: number; productRef?: string; quantity: number; unitPriceCents?: number };

// Does a single-item price-less sale name a product that has no catalog price? Only then
// does the app ask "a que precio?": a catalogued product posts at its own price, so asking
// every time would be a regression. 0/many candidates fall through to the normal path
// (not-found heals into a compound, ambiguity into a picker).
async function salePriceUnknown(op: ActionProposal): Promise<boolean> {
  const step = op.steps[0];
  if (!needsSalePrice(step)) return false;
  const items = (step.args?.items as SaleItem[] | undefined) ?? [];
  if (items.length !== 1) return false; // a multi-item sale always routes to a card
  const ref = items[0].productRef;
  if (!ref) return false;
  try {
    const r = await resolveActiveProduct(ref);
    return r.candidateCount === 1 && r.product != null && r.product.unitPriceCents == null;
  } catch {
    return false;
  }
}

// Re-derive the pending sale that an earlier turn of this flow left without a price, from
// the server's own record of the operator's turns (never a client-supplied shape). The
// fallback parser is pure and deterministic, so it recovers the sale shape for completion.
function pendingSaleFromFlow(priorTurns: string[]): ActionProposal | null {
  for (let i = priorTurns.length - 1; i >= 0; i--) {
    const p = fallbackParse(priorTurns[i]);
    if (p && isAction(p) && needsSalePrice(p.steps[0])) return p;
  }
  return null;
}

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user) return fail("unauthorized", "Sign in required", 401);
  const dbErr = requireDb();
  if (dbErr) return dbErr;

  let body: { message?: string; turnNonce?: string; flowNonce?: string; history?: unknown };
  try {
    body = await req.json();
  } catch {
    return fail("bad_json", "Request body must be JSON");
  }
  const message = (body.message ?? "").trim();
  if (!message) return fail("empty_message", "El mensaje esta vacio");

  // The active flow. The client mints a flow nonce and echoes it while the flow stays open
  // (a "needs" exchange); it rotates to a fresh one once a turn produces a terminal
  // response, so grounding is bounded to the operator's own turns in THIS flow only. A
  // bounded role-tagged transcript (body.history) may ride along for resume context; it is
  // never used for grounding — only the server record below is.
  const flowNonce = body.flowNonce && String(body.flowNonce).trim() ? String(body.flowNonce) : crypto.randomUUID();
  // Bind the server-authenticated turn record to the authenticated operator (D-052): "the
  // operator's own turns" is the same principal, not merely "whatever was written under
  // this nonce". A reused/known nonce from another session reads/writes a different owner.
  const owner = session.user.email ?? session.user.name ?? "owner";
  const turnNonce = body.turnNonce ?? crypto.randomUUID();

  try {
    // THE BRAIN SEAM (spec 010 M1, D-058). The native tool-use gateway is the primary brain:
    // it understands the whole turn and drives the MCP read tools. parseMessage is reached ONLY
    // on gateway error or timeout (AC1/AC15). When BEANS_AGENT_URL is unset (the prod default
    // until M6 deploys the box), gatewayConfigured() is false and the route is byte-identical to
    // the spec-009 parser path below, so M1 is inert in prod.
    if (gatewayConfigured()) {
      // GO-LIVE ORDERING (M6, Kaze council): the gateway is read-only in M1. Do not set
      // BEANS_AGENT_URL in prod until the M3 write-preview tools land and the system prompt
      // tells the box to leave write intents to the staging path — otherwise a configured
      // gateway would answer a write turn in prose and the proposal/auto-post path (below)
      // would be skipped. M1 ships this branch dark (env unset), so this is inert in prod.
      //
      // Record the operator's own turn as the grounding source BEFORE the box runs (D-061): the
      // write path (M3) reads operator_turns from inside the gateway's tool loop, never the
      // model's tool args, so the current turn must be in the record before /run-agent is hit.
      // Note vs spec-009 (Winston council): in configured mode a pure read turn is recorded here
      // (the parser path returns from dispatchQuery before its append). Immaterial — the flow
      // nonce rotates on a terminal response, so a read turn never pollutes a later op's corpus.
      await appendOperatorTurn(owner, flowNonce, message);
      const g = await gatewayAnswer({ utterance: message, turnNonce, signal: AbortSignal.timeout(agentTimeoutMs()) });
      if (g.answered) {
        return ok({ kind: "answer", reply: g.reply, flow_nonce: flowNonce, flow_open: false });
      }
      // Gateway did not answer (unconfigured never happens here; error/timeout/empty do): fall
      // through to the deterministic parser (D-063). The turn is already recorded above, so the
      // helper must not record it again.
      return await runParserTurn({ message, owner, flowNonce, turnNonce, alreadyRecorded: true });
    }
    // Gateway not configured: the spec-009 parser path, unchanged.
    return await runParserTurn({ message, owner, flowNonce, turnNonce, alreadyRecorded: false });
  } catch (e) {
    return fail("chat_failed", (e as Error).message, 422);
  }
}

// The deterministic parser path (spec 009), unchanged in behavior — now reached as the fallback
// when the gateway is off or fails (D-058/D-063). `alreadyRecorded` is true only when the
// configured gateway already appended this operator turn before failing, so this helper does not
// double-record it; priorTurns still means "every turn before the current one" in both cases.
async function runParserTurn(opts: {
  message: string;
  owner: string;
  flowNonce: string;
  turnNonce: string;
  alreadyRecorded: boolean;
}) {
  const { message, owner, flowNonce, turnNonce, alreadyRecorded } = opts;

  // 1. Read-only query, dispatched before the write path. Writes nothing. Closes the flow.
  const q = await dispatchQuery(message);
  if (q) return ok({ kind: "answer", reply: q.reply, query_id: q.queryId, flow_nonce: flowNonce, flow_open: false });

  // Record this operator turn in the server-authenticated flow record (unless the gateway path
  // already did), so the corpus includes the current turn. Then build the grounding corpus from
  // the server's record only (D-052), bounded to the operator and the recent active flow (TTL
  // inside flow-turns.ts). priorTurns is every turn BEFORE the current one — captured before the
  // append here, or by dropping the already-recorded last turn — so the completion path recovers
  // a pending sale the same way regardless of which brain ran first. It is TTL-bounded so a stale
  // flow cannot complete a sale the operator did not intend now.
  const recorded = (await operatorTurnsFor(owner, flowNonce)).map((t) => t.text);
  const priorTurns = alreadyRecorded ? recorded.slice(0, -1) : recorded;
  if (!alreadyRecorded) await appendOperatorTurn(owner, flowNonce, message);
  const groundingCorpus = await groundingCorpusFor(owner, flowNonce);

  {
    // 2. Parse into an action proposal (ordered steps).
    let proposal = await parseMessage(message);

    // Multi-turn price completion (AC11): a lone POSITIVE price answer ("32", "$32", "a 32")
    // with a pending price-less sale recently in THIS flow completes that sale. The qty
    // grounds to the earlier turn, the price to this one — both to the operator's own
    // recorded turns (within the TTL window). A non-positive answer never completes a sale.
    if (!proposal) {
      const price = priceAnswer(message);
      if (price !== null && price > 0) {
        const pending = pendingSaleFromFlow(priorTurns);
        // The current turn is the utterance (so the bare-confirmation guard reads THIS
        // turn); the flow corpus grounds the numerals separately via stageOperation.
        if (pending) proposal = actionOf(applySalePrice(pending.steps[0], price), message, "fallback");
      }
    }

    if (!proposal) {
      return ok({
        kind: "unparsed",
        reply: "No pude interpretar eso como una operacion. Proba, por ejemplo: 'vendi 2 medias a 300', 'gaste 500 en envio', 'llegaron 10 termos', o preguntame 'cuanto vendi hoy'.",
        flow_nonce: flowNonce,
        flow_open: false,
      });
    }
    // Forward-compat: a parser-emitted query arm. Today reads are caught by dispatchQuery
    // above; this guard narrows the type and routes a future parser-emitted query.
    if (isQuery(proposal)) {
      return ok({ kind: "unparsed", reply: "No encontre ese dato.", flow_nonce: flowNonce, flow_open: false });
    }

    // Missing-price ask (AC11): a sale naming an unpriced product has nothing to post, so
    // the app asks for the price and keeps the flow OPEN. The next lone-number turn
    // completes it (handled above). Nothing is staged; the flow record already holds this
    // turn, so the completion grounds the quantity against it.
    if (await salePriceUnknown(proposal)) {
      return ok({
        kind: "needs",
        field: "price",
        reply: "A que precio?",
        flow_nonce: flowNonce,
        flow_open: true,
      });
    }

    // Strip EVERY model-supplied id so the parser proposes descriptors only (D-050 / AC4);
    // the server mints and threads ids itself on the compound re-stage or picker.
    const step = stripModelIds(proposal.steps[0]);

    // 3. Stage the first step. The app re-derives the verdict, grounding numerals and the
    //    product name against the server-authenticated flow corpus (D-052), not the single
    //    utterance; nothing is written yet.
    const staged = await stageOperation({
      operationType: step.operationType,
      args: step.args,
      utterance: proposal.utterance,
      turnNonce,
      groundingCorpus,
    });

    if (!staged.ok) {
      // Disambiguation (AC5): a descriptor matched more than one row. Return a picker.
      if (staged.code === "ambiguous_reference" && "candidates" in staged) {
        return ok({
          kind: "disambiguation",
          operation_type: staged.operation_type,
          id_field: staged.id_field,
          candidates: staged.candidates,
          pending_args: staged.pending_args,
          utterance: proposal.utterance,
          turn_nonce: turnNonce,
          flow_nonce: flowNonce,
          flow_open: false,
        });
      }
      // Compound heal (AC1): a product-not-found on a stock or sale becomes a two-step
      // create-then-act. The step stays the commit unit (AC3): no cross-step transaction.
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
              flow_nonce: flowNonce,
              flow_open: false,
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
      flow_nonce: flowNonce,
      flow_open: false,
    });
  }
}
