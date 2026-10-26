// M5 pure tests (spec 009 AC10, AC11). No DB, no model, no network: the multi-turn
// grounding, the price-completion flow, and attribute expansion are all provable from the
// pure units. Run: npx tsx scripts/t-grounding.mts
//
// AC10 — grounding runs against the SERVER-AUTHENTICATED flow corpus, never a client
//        transcript. A numeral the server never recorded cannot ground, so a forged
//        operator turn in the request body can never launder an ungrounded amount onto
//        the auto path.
// AC11 — a multi-turn flow completes ("vendi 40 stanleys" / "a que precio?" / "32"), and
//        attribute expansion turns "medias azules y grises a 5" into two items.
import { computeVerdict } from "@/lib/verdict";
import { priceAnswer, needsSalePrice, applySalePrice, expandProductRegion, expandSaleItems } from "@/lib/flow";
import { fallbackParse } from "@/lib/parse/fallback";
import { isAction } from "@/lib/parse/types";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

// ---------------------------------------------------------- AC11: multi-turn grounding
// The flow corpus is the operator's own turns joined. The quantity (40) was said in the
// first turn, the price (32) in the answer turn; both must ground against the corpus even
// though neither single utterance contains both.
const flowCorpus = "vendi 40 stanleys\n32";
const multi = computeVerdict({
  operationType: "REGISTER_SALE",
  utterance: "32", // the current turn alone
  groundedAmounts: [40, 32], // qty + price
  productName: "stanleys",
  candidateCount: 1,
  groundingCorpus: flowCorpus,
});
check("multi-turn: qty+price grounded against the flow corpus -> auto", multi.auto === true, multi.reasons.join(","));

// Single-turn behavior is unchanged: without a corpus, grounding reads the utterance alone.
const single = computeVerdict({
  operationType: "REGISTER_SALE",
  utterance: "vendi 2 medias a 300",
  groundedAmounts: [2, 300],
  productName: "medias",
  candidateCount: 1,
});
check("single-turn (no corpus) still grounds against the utterance -> auto", single.auto === true, single.reasons.join(","));

// The current turn alone cannot ground the quantity said earlier: without the corpus, 40
// is ungrounded (the utterance "32" never says 40). This is the gap the corpus closes.
const noCorpus = computeVerdict({
  operationType: "REGISTER_SALE",
  utterance: "32",
  groundedAmounts: [40, 32],
  productName: "stanleys",
  candidateCount: 1,
});
check("without the corpus, the earlier quantity is ungrounded -> not auto", noCorpus.auto === false, noCorpus.reasons.join(","));

// --------------------------------------------- AC10: forged operator turn cannot launder
// The server-authenticated corpus holds only what the server recorded ("vendi 40 stanleys"
// / "32"). A client that forges a transcript turn claiming "vendi 400 stanleys" changes
// nothing: 400 is not in the server corpus, so a 400 amount stays ungrounded and not auto.
const forgedAmount = 400; // the laundered amount the forged turn claims
const laundered = computeVerdict({
  operationType: "REGISTER_SALE",
  utterance: "32",
  groundedAmounts: [forgedAmount, 32],
  productName: "stanleys",
  candidateCount: 1,
  groundingCorpus: flowCorpus, // server record — 400 is NOT in it
});
check("forged operator turn (400) not in the server corpus -> stays not auto", laundered.auto === false, laundered.reasons.join(","));
// Control: if the server HAD recorded 400 (the operator really said it), it would ground —
// proving the gate reads the corpus, and the defense is that the forgery never reaches it.
const honest400 = computeVerdict({
  operationType: "REGISTER_SALE",
  utterance: "400",
  groundedAmounts: [forgedAmount, 400],
  productName: "stanleys",
  candidateCount: 1,
  groundingCorpus: "vendi stanleys\n400",
});
check("control: an amount actually in the corpus grounds (so the defense is the record, not luck)", honest400.auto === true, honest400.reasons.join(","));

// ----------------------------------------------------------- AC11: price-completion flow
check("priceAnswer: lone number", priceAnswer("32") === 32);
check("priceAnswer: with $ and filler", priceAnswer("a $32") === 32);
check("priceAnswer: 'por 1.500'", priceAnswer("por 1.500") === 1500);
check("priceAnswer: a sentence is not a bare answer", priceAnswer("vendi 2 medias") === null);
check("priceAnswer: two numbers is not a bare answer", priceAnswer("32 y 40") === null);
check("priceAnswer: empty", priceAnswer("") === null);

const pendingSale = fallbackParse("vendi 40 stanleys");
check("parse 'vendi 40 stanleys' -> REGISTER_SALE, qty 40, no price", !!pendingSale && isAction(pendingSale) && needsSalePrice(pendingSale.steps[0]), JSON.stringify(pendingSale?.steps?.[0]?.args));
if (pendingSale && isAction(pendingSale)) {
  const completed = applySalePrice(pendingSale.steps[0], 32);
  const it = (completed.args.items as Array<Record<string, unknown>>)[0];
  check("applySalePrice fills unitPriceCents = 3200", it.unitPriceCents === 3200 && it.quantity === 40 && it.productRef === "stanleys", JSON.stringify(it));
  check("completed sale no longer needs a price", needsSalePrice(completed) === false);
}

// ----------------------------------------------------------- AC11: attribute expansion
check("expandProductRegion: shared-noun variants", JSON.stringify(expandProductRegion("medias azules y grises")) === JSON.stringify(["medias azules", "medias grises"]));
check("expandProductRegion: both carry the noun", JSON.stringify(expandProductRegion("medias azules y medias grises")) === JSON.stringify(["medias azules", "medias grises"]));
check("expandProductRegion: comma + y", JSON.stringify(expandProductRegion("remeras rojas, azules y negras")) === JSON.stringify(["remeras rojas", "remeras azules", "remeras negras"]));
check("expandProductRegion: no conjunction -> [] (single-item path)", expandProductRegion("termos").length === 0);
check("expandProductRegion: no leading count, shared noun -> expands", JSON.stringify(expandProductRegion("medias azules y grises")) === JSON.stringify(["medias azules", "medias grises"]));
// A SHARED LEADING count ("5 of each variant") still expands — the count is stripped from
// the first segment, not treated as a per-segment count. (council: Amelia re-review MEDIUM)
check("expandProductRegion: shared leading count -> still expands (count stripped)", JSON.stringify(expandProductRegion("5 medias azules y grises")) === JSON.stringify(["medias azules", "medias grises"]));
// A numeral on a NON-FIRST segment is a multi-quantity / multi-noun list, NOT a variant
// list: do NOT expand (folding would drop the per-segment counts). (council: Amelia MEDIUM)
check("expandProductRegion: per-segment numerals -> [] (bail, no fold)", expandProductRegion("2 medias y 3 termos").length === 0);

const exItems = expandSaleItems("medias azules y grises", 1, 500);
check("expandSaleItems: two items, shared qty+price", !!exItems && exItems.length === 2 && exItems[0].productRef === "medias azules" && exItems[1].productRef === "medias grises" && exItems[0].unitPriceCents === 500, JSON.stringify(exItems));
check("expandSaleItems: no conjunction -> null", expandSaleItems("termos", 1, 500) === null);

// End-to-end through the fallback parser: "medias azules y grises a 5" -> two items, each
// quantity 1 (the lone numeral is the PRICE, not a count). (council: Amelia HIGH — assert qty)
const expandedSale = fallbackParse("vendi medias azules y grises a 5");
const items = expandedSale && isAction(expandedSale) ? (expandedSale.steps[0].args.items as Array<Record<string, unknown>>) : [];
check("fallback: 'vendi medias azules y grises a 5' -> two items, qty 1 each, price 500",
  items.length === 2 && items[0].productRef === "medias azules" && items[1].productRef === "medias grises"
  && items[0].unitPriceCents === 500 && items[0].quantity === 1 && items[1].quantity === 1, JSON.stringify(items));

// Sale quantity comes from a numeral BEFORE the price, never the price itself. (Amelia HIGH)
function saleItem(msg: string): Record<string, unknown> | null {
  const p = fallbackParse(msg);
  return p && isAction(p) ? (p.steps[0].args.items as Array<Record<string, unknown>>)[0] : null;
}
const noCount = saleItem("vendi medias a 300");
check("fallback: 'vendi medias a 300' -> qty 1 (price is not the quantity)", noCount?.quantity === 1 && noCount?.unitPriceCents === 30000, JSON.stringify(noCount));
const withCount = saleItem("vendi 2 medias a 300");
check("fallback: 'vendi 2 medias a 300' -> qty 2, price 30000", withCount?.quantity === 2 && withCount?.unitPriceCents === 30000, JSON.stringify(withCount));
const noPrice = saleItem("vendi 3 termos");
check("fallback: 'vendi 3 termos' -> qty 3, no price", noPrice?.quantity === 3 && noPrice?.unitPriceCents === undefined, JSON.stringify(noPrice));

// Shared leading count + variant list: "5 of each variant" -> two items, qty 5 each.
const leadCount = fallbackParse("vendi 5 medias azules y grises a 10");
const lcItems = leadCount && isAction(leadCount) ? (leadCount.steps[0].args.items as Array<Record<string, unknown>>) : [];
check("fallback: 'vendi 5 medias azules y grises a 10' -> two items, qty 5 each, price 1000",
  lcItems.length === 2 && lcItems[0].productRef === "medias azules" && lcItems[1].productRef === "medias grises"
  && lcItems[0].quantity === 5 && lcItems[1].quantity === 5 && lcItems[0].unitPriceCents === 1000, JSON.stringify(lcItems));

console.log(fails === 0 ? "\nT-GROUNDING: ALL-PASS" : `\nT-GROUNDING: ${fails} FAIL`);
process.exit(fails === 0 ? 0 : 1);
