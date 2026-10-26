// Named test for spec 010 M5 T-022 (AC-T re the confirm-only tools): the confirm-only write
// tools (update_product_price, register_product, register_products_batch, deactivate_product,
// cancel_last_operation) are wired through the stage path AND stay confirm-only. PURE: no DB, no
// model, no network. Run: npx tsx scripts/t-confirm-tools.mts
//
// Two properties this proves:
//   1. mapPreviewTool turns each confirm-only tool call into the right registry op input
//      (and rejects bad args cleanly), including the batch fan-out and its BATCH_MAX bound.
//   2. Every confirm-only op's verdict is auto:false regardless of how well-grounded the turn
//      looks: an irreversible / requiresHumanReview op can never be promoted onto the auto path.
//      This is the "stay confirm-only" half of the AC, checked at computeVerdict, the proof.
import { mapPreviewTool, BATCH_MAX } from "@/lib/internal/preview-map";
import { OPS, pickNewestOperation, toMs, type LastOpCandidate } from "@/lib/ops/registry";
import { computeVerdict } from "@/lib/verdict";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

// --- 1. update_product_price maps to UPDATE_PRICE with cents + descriptor ----------------------
const up = mapPreviewTool("update_product_price", { product: "medias", new_amount: 350 });
check("update_product_price -> UPDATE_PRICE", up.ok && "input" in up && up.input.operationType === "UPDATE_PRICE", JSON.stringify(up));
check("  ...whole units -> cents (350 -> 35000)", up.ok && "input" in up && up.input.args.unitPriceCents === 35000, JSON.stringify(up));
check("  ...carries the product descriptor, never an id", up.ok && "input" in up && up.input.args.productRef === "medias" && !("productId" in up.input.args), JSON.stringify(up));
const upBad = mapPreviewTool("update_product_price", { product: "", new_amount: 10 });
check("update_product_price with no product -> clean error", !upBad.ok && "code" in upBad && upBad.code === "bad_tool_args", JSON.stringify(upBad));
const upNeg = mapPreviewTool("update_product_price", { product: "x", new_amount: -5 });
check("update_product_price with a negative amount -> clean error", !upNeg.ok, JSON.stringify(upNeg));

// --- 2. register_product maps to REGISTER_PRODUCT and KEEPS the stated price (not price-pending) -
const rp = mapPreviewTool("register_product", { name: "Termo 1L", price_amount: 1200, cost_amount: 700 });
check("register_product -> REGISTER_PRODUCT", rp.ok && "input" in rp && rp.input.operationType === "REGISTER_PRODUCT", JSON.stringify(rp));
check("  ...keeps the stated price (1200 -> 120000 cents)", rp.ok && "input" in rp && rp.input.args.unitPriceCents === 120000, JSON.stringify(rp));
check("  ...keeps the stated cost (700 -> 70000 cents)", rp.ok && "input" in rp && rp.input.args.unitCostCents === 70000, JSON.stringify(rp));
const rpNoPrice = mapPreviewTool("register_product", { name: "x" });
check("register_product with no price -> clean error", !rpNoPrice.ok, JSON.stringify(rpNoPrice));

// --- 3. register_products_batch fans out to N REGISTER_PRODUCT ops; BATCH_MAX bounds it ---------
const batch = mapPreviewTool("register_products_batch", { products: [
  { name: "A", price_amount: 100 },
  { name: "B", price_amount: 200, cost_amount: 50 },
] });
check("register_products_batch -> batch of 2", batch.ok && "batch" in batch && batch.batch.length === 2, JSON.stringify(batch));
check("  ...each is a REGISTER_PRODUCT", batch.ok && "batch" in batch && batch.batch.every((b) => b.operationType === "REGISTER_PRODUCT"), "");
check("  ...prices preserved", batch.ok && "batch" in batch && batch.batch[0].args.unitPriceCents === 10000 && batch.batch[1].args.unitPriceCents === 20000, "");
const batchEmpty = mapPreviewTool("register_products_batch", { products: [] });
check("empty batch -> clean error", !batchEmpty.ok, JSON.stringify(batchEmpty));
const batchOver = mapPreviewTool("register_products_batch", { products: Array.from({ length: BATCH_MAX + 1 }, (_, i) => ({ name: `p${i}`, price_amount: 1 })) });
check(`batch over BATCH_MAX (${BATCH_MAX}) -> clean error`, !batchOver.ok, JSON.stringify(batchOver));
const batchBadItem = mapPreviewTool("register_products_batch", { products: [{ name: "ok", price_amount: 1 }, { name: "", price_amount: 2 }] });
check("batch with one bad item -> whole set fails (nothing staged ambiguously)", !batchBadItem.ok, JSON.stringify(batchBadItem));

// --- 4. deactivate_product and cancel_last_operation map to their registry ops ------------------
const de = mapPreviewTool("deactivate_product", { product: "termo viejo" });
check("deactivate_product -> DEACTIVATE_PRODUCT with descriptor", de.ok && "input" in de && de.input.operationType === "DEACTIVATE_PRODUCT" && de.input.args.productRef === "termo viejo", JSON.stringify(de));
const cl = mapPreviewTool("cancel_last_operation", {});
check("cancel_last_operation -> CANCEL_LAST, no model args", cl.ok && "input" in cl && cl.input.operationType === "CANCEL_LAST" && Object.keys(cl.input.args).length === 0, JSON.stringify(cl));
const unknown = mapPreviewTool("set_db_url", { url: "x" });
check("an unknown tool -> unsupported_tool error", !unknown.ok && "code" in unknown && unknown.code === "unsupported_tool", JSON.stringify(unknown));

// --- 5. pickNewestOperation: cross-type newest by epoch millis, from the REAL runtime types -----
// The bug council caught: sale/expense createdAt hydrate as Date objects, stock occurredAt as a raw
// pg string "YYYY-MM-DD HH:MM:SS+00". Build candidates via toMs from exactly those shapes (NOT ISO
// literals) so the test exercises what resolve() actually produces.
const saleDate = new Date("2026-10-26T10:00:00.000Z");          // Date object (sale/expense shape)
const expenseDate = new Date("2026-10-26T12:00:00.000Z");       // Date object, the latest
const stockPg = "2026-10-26 09:00:00.123+00";                   // raw pg string (stock shape)
const sale: LastOpCandidate = { kind: "sale", id: 1, label: "la venta #1", whenMs: toMs(saleDate) };
const expense: LastOpCandidate = { kind: "expense", id: 2, label: "el gasto #2", whenMs: toMs(expenseDate) };
const stock: LastOpCandidate = { kind: "stock", id: 3, label: "stock #3", whenMs: toMs(stockPg) };
check("toMs parses a Date object", Number.isFinite(sale.whenMs) && sale.whenMs === saleDate.getTime());
check("toMs parses a raw pg timestamp string", Number.isFinite(stock.whenMs) && stock.whenMs === Date.parse("2026-10-26T09:00:00.123Z"), String(stock.whenMs));
check("pickNewest across mixed types -> the latest (expense, 12:00) not a letter-leading string", pickNewestOperation([sale, expense, stock])?.kind === "expense", "");
// The exact misfire the bug produced: an EARLIER stock (pg string, digit-leading) vs a LATER sale
// (Date, letter-leading as a string). Chronologically the sale (10:00) is newer than stock (09:00).
check("later sale beats earlier stock despite mixed string shapes", pickNewestOperation([sale, stock])?.kind === "sale", "");
check("pickNewest with only a sale present -> the sale", pickNewestOperation([sale, null, null])?.kind === "sale", "");
check("pickNewest with nothing -> null", pickNewestOperation([null, null, null]) === null, "");
check("pickNewest drops a candidate with an unparseable timestamp (NaN whenMs)", pickNewestOperation([{ ...sale, whenMs: toMs("not-a-date") }, stock])?.kind === "stock", "");

// --- 6. STAY CONFIRM-ONLY: every confirm-only op is auto:false even with a flawless grounding ----
// The strongest possible auto case (reversible-looking grounding) must still NOT auto-post for a
// confirm-only op, because the registry stamp (irreversible / requiresHumanReview) is honored first.
const confirmOnly = ["UPDATE_PRICE", "REGISTER_PRODUCT", "DEACTIVATE_PRODUCT", "CANCEL_LAST", "CANCEL_SALE", "CANCEL_EXPENSE", "CANCEL_STOCK"];
for (const type of confirmOnly) {
  const op = OPS[type];
  const v = computeVerdict({
    operationType: type,
    utterance: "vendi 2 medias a 300", // a perfectly-grounded-looking single turn
    groundedAmounts: [],
    productName: null,
    candidateCount: 1,
    withinCaps: true,
    irreversible: op.irreversible,
    requiresHumanReview: op.requiresHumanReview,
    groundingCorpus: "vendi 2 medias a 300",
  });
  check(`${type} stays confirm-only (auto:false, human review)`, v.auto === false && v.requiresHumanReview === true, v.reasons.join(","));
}

console.log(fails === 0 ? "\nT-CONFIRM-TOOLS: ALL-PASS" : `\nT-CONFIRM-TOOLS: ${fails} FAIL`);
process.exit(fails === 0 ? 0 : 1);
