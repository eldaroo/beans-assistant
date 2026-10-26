// Named test for spec 010 M4 T-019 (AC14, D-064 / D-057): the multi-turn-confirm consent gate.
// PURE: no DB, no model, no network. Run: npx tsx scripts/t-multi-turn-consent.mts
//
// THE RULE (D-064, retaining D-057): an op whose load-bearing grounding spans more than the
// current turn never auto-posts. "vendi 40 stanleys" then (asked a price) "32" assembles a sale
// across two turns. The grounding still succeeds against the server-authenticated flow corpus
// (that mechanism, spec 009 M5, is unchanged), but the owner never saw "40 stanleys at 32" as an
// assembled whole, so they must assent to it on a final confirm card. computeVerdict forces
// auto:false whenever a load-bearing fact (a numeral or the product name) is grounded only by an
// earlier turn. A single-turn write, where grounding and consent coincide, auto-posts as before.
import { computeVerdict } from "@/lib/verdict";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

// --- 1. The canonical AC14 case: a sale assembled across turns CONFIRMS, never auto-posts. ----
// Flow: turn 1 "vendi 40 stanleys" (no price) -> the app asks "a que precio?" -> turn 2 "32".
// The corpus is both turns; the current turn is "32" alone. The quantity (40) and the product
// name are grounded only by the earlier turn, so the consent gate fires.
const assembled = computeVerdict({
  operationType: "REGISTER_SALE",
  utterance: "32",
  groundedAmounts: [40, 32],
  productName: "stanleys",
  candidateCount: 1,
  withinCaps: true,
  groundingCorpus: "vendi 40 stanleys\n32",
});
check("multi-turn-assembled sale -> auto:false (confirms on a final card)", assembled.auto === false, assembled.reasons.join(","));
check("  ...the reason is the consent gate, not ungrounded/ambiguous/bare",
  assembled.reasons.includes("multi-turn-consent-gate")
    && !assembled.reasons.some((r) => r.startsWith("ungrounded-numerals"))
    && !assembled.reasons.some((r) => r.startsWith("ambiguous"))
    && !assembled.reasons.includes("bare-confirmation"),
  assembled.reasons.join(","));
check("  ...and it requires human review", assembled.requiresHumanReview === true, JSON.stringify(assembled));

// --- 2. Single-turn control: the SAME facts typed in one message auto-post (consent coincides
// with grounding). This proves the gate keys on "spans more than the current turn", not on the
// mere presence of a corpus or on multi-turn flows in general.
const oneTurn = computeVerdict({
  operationType: "REGISTER_SALE",
  utterance: "vendi 40 stanleys a 32",
  groundedAmounts: [40, 32],
  productName: "stanleys",
  candidateCount: 1,
  withinCaps: true,
  groundingCorpus: "vendi 40 stanleys a 32",
});
check("single-turn sale with the same facts -> auto:true", oneTurn.auto === true, oneTurn.reasons.join(","));

// --- 3. The current turn RE-STATES the whole op even though an earlier turn exists: still auto.
// A prior unrelated turn is in the corpus, but the current utterance alone grounds every
// load-bearing fact, so consent and grounding coincide -> auto. The gate must not over-fire on
// any flow that merely has history.
const restated = computeVerdict({
  operationType: "REGISTER_SALE",
  utterance: "vendi 2 medias a 300",
  groundedAmounts: [2, 300],
  productName: "medias",
  candidateCount: 1,
  withinCaps: true,
  groundingCorpus: "hola\nvendi 2 medias a 300",
});
check("current turn re-states the whole op (history present) -> auto:true", restated.auto === true, restated.reasons.join(","));

// --- 4. A pure expense assembled across turns also confirms (product-less op, the numeral spans). --
// The amount (500) was stated on an EARLIER turn ("gaste 500 en envio"); the current turn ("si, ese")
// does not restate it. So the single load-bearing fact of a product-less expense is grounded only by
// an earlier turn -> the consent gate fires -> auto:false. This proves the gate works on an op with
// no product anchor, where the numeral span alone decides consent.
const expenseAssembled = computeVerdict({
  operationType: "REGISTER_EXPENSE",
  utterance: "si, ese",
  groundedAmounts: [500],
  productName: null,
  candidateCount: 1,
  withinCaps: true,
  groundingCorpus: "gaste 500 en envio\nsi, ese",
});
check("expense whose amount spans an earlier turn -> auto:false (consent gate)",
  expenseAssembled.auto === false && expenseAssembled.reasons.includes("multi-turn-consent-gate"),
  expenseAssembled.reasons.join(","));
// (Note "si, ese" is also a near-bare turn; the gate is independent of that — it fires on the
// span, and a genuinely bare "si" is caught separately by the bare-confirmation guard.)

// --- 5. A single-turn expense where the amount is in THIS turn still auto-posts. ---------------
const expenseOneTurn = computeVerdict({
  operationType: "REGISTER_EXPENSE",
  utterance: "gaste 500 en envio",
  groundedAmounts: [500],
  productName: null,
  candidateCount: 1,
  withinCaps: true,
  groundingCorpus: "gaste 500 en envio",
});
check("single-turn expense -> auto:true", expenseOneTurn.auto === true, expenseOneTurn.reasons.join(","));

console.log(fails === 0 ? "\nT-MULTI-TURN-CONSENT: ALL-PASS" : `\nT-MULTI-TURN-CONSENT: ${fails} FAIL`);
process.exit(fails === 0 ? 0 : 1);
