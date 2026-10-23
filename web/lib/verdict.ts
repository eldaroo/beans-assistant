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

export function computeVerdict(params: {
  operationType: string;
  utterance: string;
  groundedAmounts: Array<number | string>;
  productName: string | null | undefined;
  candidateCount: number;
  withinCaps?: boolean;
  irreversible?: boolean;
}): Verdict {
  const {
    operationType,
    utterance,
    groundedAmounts,
    productName,
    candidateCount,
    withinCaps = true,
    irreversible = false,
  } = params;
  const reasons: string[] = [];
  const op = (operationType || "").toUpperCase();

  if (irreversible) {
    reasons.push("irreversible-op");
    return { auto: false, requiresHumanReview: true, reasons };
  }

  const reversible = REVERSIBLE_OPS.has(op);
  if (!reversible) reasons.push(`not-in-reversible-set:${op}`);

  const bare = isBareConfirmation(utterance);
  if (bare) reasons.push("bare-confirmation");

  const said = parseNumbers(utterance);
  const ungrounded = groundedAmounts.filter((a) => !numeralIsGrounded(a, said));
  if (ungrounded.length) reasons.push(`ungrounded-numerals:${JSON.stringify(ungrounded)}`);

  const nameGrounded = productNameGrounded(productName, utterance);
  if (!nameGrounded) reasons.push("product-not-in-utterance");

  const deterministic = candidateCount === 1;
  if (candidateCount === 0) reasons.push("no-product-match");
  else if (candidateCount > 1) reasons.push(`ambiguous-${candidateCount}-candidates`);

  if (!withinCaps) reasons.push("over-cap");

  const auto =
    reversible &&
    !bare &&
    ungrounded.length === 0 &&
    nameGrounded &&
    deterministic &&
    withinCaps;

  return { auto, requiresHumanReview: !auto, reasons };
}
