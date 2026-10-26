// The server-computed auto-post verdict. Ported verbatim from
// backend/services/write_verdict.py (spec 007 D-040/D-041/D-042).
//
// "Reversible posts, irreversible asks." A write auto-posts ONLY when the APP
// proves it safe. This module is that proof: it is pure (no DB, no network, no
// model) so it can never be talked into a yes by operator text or a hijacked model.
//
// A write may auto-post iff ALL hold:
//   (a) reversible set   - operation_type in {REGISTER_SALE, REGISTER_EXPENSE, ADD_STOCK}
//   (b) provenance       - every load-bearing numeral in the staged args appears
//                          VERBATIM in the operator's own utterance this turn, and
//                          the product name (when the op names one) appears too
//   (c) determinism      - the product resolved to exactly one active candidate
//   (d) within caps      - per-write and per-session caps hold
//   (e) single-turn consent - the load-bearing facts are all present in the CURRENT turn, not
//                          assembled across turns (D-064 / D-057): an op whose grounding spans
//                          more than this turn confirms on a final card, it never auto-posts
// A bare confirmation turn ("ok", "dale") grounds nothing, so it is never auto.

import { parseNumbers, numeralIsGrounded, tokenSet, stripAccents } from "@/lib/money";

// The only operations that may ever auto-post. Everything else (price changes,
// product registration, cancels, deactivation, batch) is confirm-only.
export const REVERSIBLE_OPS = new Set<string>([
  "REGISTER_SALE",
  "REGISTER_EXPENSE",
  "ADD_STOCK",
]);

// A turn whose entire normalized content is one of these is a bare confirmation:
// it carries no new grounded fact, so it can never carry consent for an auto-post.
const BARE_CONFIRMATIONS = new Set<string>([
  "ok", "oka", "okay", "dale", "si", "sii", "sip", "listo", "hecho", "confirmo",
  "confirmar", "va", "vale", "bueno", "perfecto", "de una", "sisi", "yes", "y", "ya",
]);

export function isBareConfirmation(utterance: string): boolean {
  let norm = stripAccents((utterance || "").trim().toLowerCase());
  norm = norm.replace(/[^\w\s]/g, "").trim();
  return BARE_CONFIRMATIONS.has(norm) || norm === "";
}

// True iff at least one meaningful word of the product name appears in the
// utterance. Accent- and case-insensitive; a one-/two-letter token does not count.
export function productNameGrounded(
  productName: string | null | undefined,
  utterance: string,
): boolean {
  if (!productName) return true; // op carries no product to ground (e.g. a pure expense)
  const utter = tokenSet(utterance);
  let nameWords = [...tokenSet(productName)].filter((w) => w.length > 2);
  if (nameWords.length === 0) nameWords = [...tokenSet(productName)].filter(Boolean);
  return nameWords.some((w) => utter.has(w));
}

export interface Verdict {
  auto: boolean;
  requiresHumanReview: boolean;
  reasons: string[];
}

// The per-turn auto-post cap (spec 010 M5, T-023, AC-T6). A single grounded operator turn can
// auto-post at most this many reversible writes. This bounds a DISTINCT risk from the per-session
// window cap in lib/audit: numeralIsGrounded is SET-MEMBERSHIP, not consumption, so one grounded
// numeral ("vendi 3") can ground three separate auto-sales the model stages from one turn. The
// session window cap (60/window) would let all of them auto-post; this cap holds the fan-out of a
// single turn to a human-sized number so a runaway or hijacked loop cannot auto-post a burst.
export const TURN_AUTO_CAP = Number(process.env.BEANS_TURN_AUTO_CAP) || 3;

// Demote a verdict to confirm-only when this turn has already auto-posted TURN_AUTO_CAP writes.
// Pure: the caller supplies the count of prior auto writes staged under the same turn nonce
// (lib/pending-ops.countAutoForTurn); this decides and records the demotion. Only an auto verdict
// is ever demoted, and only at-or-above the cap — the first `cap` auto writes of a turn are
// unaffected, so normal multi-write turns ("vendi 2 medias y 1 termo") still auto-post.
export function demoteOverTurnCap(verdict: Verdict, priorAutoCount: number, cap: number = TURN_AUTO_CAP): Verdict {
  if (verdict.auto && priorAutoCount >= cap) {
    return { auto: false, requiresHumanReview: true, reasons: [...verdict.reasons, `per-turn-write-cap:${cap}`] };
  }
  return verdict;
}

export function computeVerdict(params: {
  operationType: string;
  utterance: string;
  groundedAmounts: Array<number | string>;
  productName: string | null | undefined;
  candidateCount: number;
  withinCaps?: boolean;
  irreversible?: boolean;
  // A PERMANENT registry-level confirm-only stamp (spec 009 AC7 / s-15). It is honored
  // FIRST, before any grounding logic, so a destructive or cost-model op can never be
  // promoted onto the auto path by a future grounding change, however well-grounded a turn
  // looks. Independent of `irreversible`: the flag lives on the OpDef, not in this proof.
  requiresHumanReview?: boolean;
  // The multi-turn grounding corpus (spec 009 M5 / D-052 / AC10). When a flow spans turns
  // ("vendi 40 stanleys" then "a que precio?" then "32"), a numeral and the product name
  // may be grounded by an EARLIER operator turn than the current one. This corpus is the
  // SERVER-AUTHENTICATED record of the operator's own turns in the active flow
  // (lib/flow-turns.ts), never the client-supplied transcript — so a forged operator turn
  // in the request body cannot launder an ungrounded amount onto the auto path. It defaults
  // to the current utterance, which keeps single-turn behavior unchanged. The current
  // utterance is still what the bare-confirmation check reads: the CURRENT turn must carry
  // content, so "ok"/"dale" alone never auto-posts even when the flow corpus is rich.
  groundingCorpus?: string;
}): Verdict {
  const {
    operationType,
    utterance,
    groundedAmounts,
    productName,
    candidateCount,
    withinCaps = true,
    irreversible = false,
    requiresHumanReview: forcedHumanReview = false,
    groundingCorpus,
  } = params;
  const reasons: string[] = [];
  const op = (operationType || "").toUpperCase();
  // Grounding reads the flow corpus when given, else the current utterance alone.
  const corpus = groundingCorpus && groundingCorpus.trim() ? groundingCorpus : utterance;

  if (forcedHumanReview) {
    reasons.push("registry-human-review");
    return { auto: false, requiresHumanReview: true, reasons };
  }

  if (irreversible) {
    reasons.push("irreversible-op");
    return { auto: false, requiresHumanReview: true, reasons };
  }

  const reversible = REVERSIBLE_OPS.has(op);
  if (!reversible) reasons.push(`not-in-reversible-set:${op}`);

  const bare = isBareConfirmation(utterance);
  if (bare) reasons.push("bare-confirmation");

  const said = parseNumbers(corpus);
  const ungrounded = groundedAmounts.filter((a) => !numeralIsGrounded(a, said));
  if (ungrounded.length) reasons.push(`ungrounded-numerals:${JSON.stringify(ungrounded)}`);

  const nameGrounded = productNameGrounded(productName, corpus);
  if (!nameGrounded) reasons.push("product-not-in-utterance");

  const deterministic = candidateCount === 1;
  if (candidateCount === 0) reasons.push("no-product-match");
  else if (candidateCount > 1) reasons.push(`ambiguous-${candidateCount}-candidates`);

  if (!withinCaps) reasons.push("over-cap");

  const groundedAuto =
    reversible &&
    !bare &&
    ungrounded.length === 0 &&
    nameGrounded &&
    deterministic &&
    withinCaps;

  // CALLER INVARIANT the gate below depends on (council: Winston HIGH). The gate infers "assembled
  // across turns" from `corpus !== utterance`, so the caller MUST pass `utterance` = the CURRENT
  // operator turn only and `groundingCorpus` = the full-flow record (the join of all operator turns
  // this flow). Both callers honor it: the preview endpoint sets utterance = turns[last].text and
  // groundingCorpus = turns.join("\n"); the parser path passes proposal.utterance + the flow corpus.
  // A caller that passed utterance === groundingCorpus would silently make this gate inert, so the
  // invariant is pinned by a source-assertion in scripts/t-internal-preview.mts (grep of the route),
  // which fails loudly if a future edit collapses the two at the call site.
  //
  // D-064 / D-057 consent gate (spec 010 M4, AC14): an op whose load-bearing grounding spans
  // more than the current turn never auto-posts. When the flow corpus carries more than the
  // current utterance, the numerals or the product name may have been grounded by an EARLIER
  // operator turn ("vendi 40 stanleys" ... "32"): grounding succeeds against the corpus, but
  // the owner never saw the assembled whole ("40 stanleys at 32") in one place and so never
  // consented to it. Re-ground against the CURRENT turn alone; if a load-bearing fact is
  // grounded only by an earlier turn, force auto:false so the owner assents to the assembled
  // whole on a final confirm card. Single-turn flows are unaffected: when the corpus equals the
  // current utterance, utterance-alone grounding equals corpus grounding and the gate is inert.
  // This supersedes the spec-009 M5 behavior (a multi-turn-completed sale auto-posted); the
  // consent reason for D-057 is retained as this verdict-time gate (ARCHITECTURE D-064).
  let multiTurnConsentGate = false;
  if (groundedAuto && corpus !== utterance) {
    const saidCurrent = parseNumbers(utterance);
    const numeralsInCurrentTurn = groundedAmounts.every((a) => numeralIsGrounded(a, saidCurrent));
    const nameInCurrentTurn = productNameGrounded(productName, utterance);
    if (!numeralsInCurrentTurn || !nameInCurrentTurn) {
      multiTurnConsentGate = true;
      reasons.push("multi-turn-consent-gate");
    }
  }

  const auto = groundedAuto && !multiTurnConsentGate;

  return { auto, requiresHumanReview: !auto, reasons };
}
