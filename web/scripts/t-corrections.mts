// Named test for spec 009 M3 (AC6 the parser emits the five correction/edit intents as
// descriptors and each is confirm-only, AC7 the permanent registry-level human-review
// stamp). PURE: no DB, no network. Run: npx tsx scripts/t-corrections.mts
//
// AC7's load-bearing claim: destructive and cost ops carry requiresHumanReview at the
// REGISTRY level, independent of the dynamic verdict, so no grounding change can ever
// promote them onto the auto path. The control case proves the flag -- not the grounding
// -- is what forces confirm-only: the same perfect grounding auto-posts without the flag.
import { fallbackParse } from "@/lib/parse/fallback";
import { isAction } from "@/lib/parse/types";
import { OPS } from "@/lib/ops/registry";
import { computeVerdict } from "@/lib/verdict";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

function parse(msg: string) {
  const p = fallbackParse(msg);
  if (!p || !isAction(p)) return null;
  return p.steps[0];
}
const ID_KEYS = ["saleId", "expenseId", "movementId", "productId"];
function hasNoModelId(args: Record<string, unknown>): boolean {
  return ID_KEYS.every((k) => !(k in args));
}

// ---- AC6: the parser emits the five intents as DESCRIPTORS (never ids) ----
const cancelSale = parse("cancela la ultima venta");
check("AC6 parse CANCEL_SALE", cancelSale?.operationType === "CANCEL_SALE", JSON.stringify(cancelSale));
check("AC6 CANCEL_SALE carries a saleRef descriptor", typeof cancelSale?.args.saleRef === "string" && hasNoModelId(cancelSale!.args));

const cancelSaleNamed = parse("anula la venta de Juan");
check("AC6 'anula la venta de Juan' -> CANCEL_SALE", cancelSaleNamed?.operationType === "CANCEL_SALE" && hasNoModelId(cancelSaleNamed!.args));

const cancelExp = parse("cancela el gasto de luz");
check("AC6 parse CANCEL_EXPENSE", cancelExp?.operationType === "CANCEL_EXPENSE" && typeof cancelExp?.args.expenseRef === "string" && hasNoModelId(cancelExp!.args), JSON.stringify(cancelExp));

const cancelStock = parse("borra la entrada de termos");
check("AC6 parse CANCEL_STOCK", cancelStock?.operationType === "CANCEL_STOCK" && typeof cancelStock?.args.movementRef === "string" && hasNoModelId(cancelStock!.args), JSON.stringify(cancelStock));

const price = parse("cambia el precio de las medias a 500");
check("AC6 parse UPDATE_PRICE", price?.operationType === "UPDATE_PRICE", JSON.stringify(price));
check("AC6 UPDATE_PRICE carries productRef + grounded new price, no id", price?.args.productRef === "medias" && price?.args.unitPriceCents === 50000 && hasNoModelId(price!.args), JSON.stringify(price?.args));

const deact = parse("da de baja el termo stanley");
check("AC6 parse DEACTIVATE_PRODUCT", deact?.operationType === "DEACTIVATE_PRODUCT" && deact?.args.productRef === "termo stanley" && hasNoModelId(deact!.args), JSON.stringify(deact));

// a cancel must not be swallowed by the sale/expense/stock write intents
check("AC6 'cancela la venta' is NOT a REGISTER_SALE", parse("cancela la venta de 2 medias")?.operationType === "CANCEL_SALE");

// ---- AC7: the five destructive/edit ops carry the PERMANENT registry flag ----
for (const op of ["CANCEL_SALE", "CANCEL_EXPENSE", "CANCEL_STOCK", "UPDATE_PRICE", "DEACTIVATE_PRODUCT"]) {
  check(`AC7 ${op} is requiresHumanReview at the registry`, OPS[op].requiresHumanReview === true);
}
// the auto-postable write ops are NOT flagged (the stamp is scoped, not blanket)
for (const op of ["REGISTER_SALE", "REGISTER_EXPENSE", "ADD_STOCK"]) {
  check(`AC7 ${op} is NOT registry-flagged`, !OPS[op].requiresHumanReview);
}

// ---- AC7: the flag forces confirm-only even under PERFECT grounding ----
// A turn that would otherwise auto-post: reversible-looking, grounded numeral, product in
// the utterance, single candidate, within caps. With the registry flag it still asks.
const perfect = {
  utterance: "medias 500",
  groundedAmounts: [500] as Array<number | string>,
  productName: "medias",
  candidateCount: 1,
  withinCaps: true,
  irreversible: false,
};
const forced = computeVerdict({ operationType: "UPDATE_PRICE", requiresHumanReview: true, ...perfect });
check("AC7 flagged op never auto-posts under perfect grounding", forced.auto === false && forced.requiresHumanReview === true, JSON.stringify(forced));
check("AC7 the reason names the registry stamp", forced.reasons.includes("registry-human-review"));

// control: the SAME perfect grounding on a reversible op WITHOUT the flag DOES auto-post,
// proving the flag -- not the grounding -- is what forces confirm-only.
const control = computeVerdict({ operationType: "REGISTER_SALE", ...perfect });
check("AC7 control: same grounding auto-posts without the flag", control.auto === true, JSON.stringify(control));

// none of the five auto-posts, whatever the grounding
for (const op of ["CANCEL_SALE", "CANCEL_EXPENSE", "CANCEL_STOCK", "UPDATE_PRICE", "DEACTIVATE_PRODUCT"]) {
  const v = computeVerdict({ operationType: op, requiresHumanReview: true, ...perfect });
  check(`AC7 ${op} never auto-posts`, v.auto === false);
}

console.log(fails ? `\n${fails} FAILED` : "\nALL PASS");
process.exit(fails ? 1 : 0);
