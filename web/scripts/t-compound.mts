// Named test for spec 009 M1 (AC1 compound create-then-act, AC2 minimal mint, AC3 the
// step stays the unit of commit). PURE: no DB, no network. Run: npx tsx scripts/t-compound.mts
//
// AC3's load-bearing claim is the atomicity one: "a late-step failure leaves earlier
// committed steps intact and does not strand a partial." driveCompound encodes that, and
// the injected-failure case below pins it.
import { mintMinimalProductArgs, deriveSkuStem } from "@/lib/ops/mint";
import { buildCompoundSteps, productRefOfStep, threadProductId, driveCompound, isCompoundableAct, stripModelProductIds } from "@/lib/ops/compound";
import { actionOf, isAction, isQuery } from "@/lib/parse/types";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

// --- AC2: a name alone mints a minimal product (derived sku, unit cost 0, price pending)
const minted = mintMinimalProductArgs("Pulseras Rojas", "ab12");
check("AC2 mint derives a slug sku", minted.sku === "pulseras-rojas-ab12", minted.sku);
check("AC2 mint unit cost is 0", minted.unitCostCents === 0);
check("AC2 mint price is pending (null)", minted.unitPriceCents === null);
check("AC2 mint keeps the name", minted.name === "Pulseras Rojas");
check("AC2 slug strips accents and punctuation", deriveSkuStem("Medias Azules!! ñoño") === "medias-azules-nono", deriveSkuStem("Medias Azules!! ñoño"));

// --- AC1: an unresolved stock/sale builds a two-step compound with the right shape
const stockStep = { operationType: "ADD_STOCK", args: { productRef: "pulseras rojas", quantity: 50 } };
check("AC1 ADD_STOCK is compoundable", isCompoundableAct("ADD_STOCK"));
check("AC1 REGISTER_EXPENSE is NOT compoundable", !isCompoundableAct("REGISTER_EXPENSE"));
// C1 heals stock only; create-then-sell is deferred (a minted product has no stock/price,
// so a PAID sale of it can never commit). Pinning the decision so it cannot silently return.
check("C1 REGISTER_SALE is NOT an auto-heal act (sale-heal deferred)", !isCompoundableAct("REGISTER_SALE"));
const ref = productRefOfStep(stockStep);
check("AC1 product ref extracted from stock step", ref === "pulseras rojas", String(ref));
const compound = buildCompoundSteps(stockStep, ref!);
check("AC1 step 1 is REGISTER_PRODUCT", compound.register.operationType === "REGISTER_PRODUCT");
check("AC1 step 1 carries the name for the mint", compound.register.args.name === "pulseras rojas");
check("AC1 step 2 is the original act verbatim", compound.act.operationType === "ADD_STOCK");

// --- D-050: the id is threaded server-side; the model never supplies it
const threadedStock = threadProductId(stockStep, 77);
check("threaded stock carries productId", threadedStock.args.productId === 77);
check("threaded stock drops the unresolved ref", threadedStock.args.productRef === undefined);
const saleStep = { operationType: "REGISTER_SALE", args: { items: [{ productRef: "pulseras rojas", quantity: 3, unitPriceCents: 50000 }] } };
const threadedSale = threadProductId(saleStep, 88);
const saleItem = (threadedSale.args.items as Array<Record<string, unknown>>)[0];
check("threaded sale item carries productId", saleItem.productId === 88);
check("threaded sale item drops the ref", saleItem.productRef === undefined);
check("threaded sale item keeps quantity + price", saleItem.quantity === 3 && saleItem.unitPriceCents === 50000);
const refFromSale = productRefOfStep(saleStep);
check("AC1 product ref extracted from sale item", refFromSale === "pulseras rojas", String(refFromSale));

// --- AC3 happy path: both steps commit in order, step 2 threaded to step 1's product id
async function happy() {
  let stagedWith = -1;
  const outcomes = await driveCompound({
    confirmRegister: async () => ({ id: 101, name: "pulseras rojas" }),
    stageAct: async (productId) => { stagedWith = productId; return { op_token: "tok-2" }; },
    confirmAct: async (opToken) => ({ committed: true, opToken }),
  });
  check("AC3 happy: step 1 committed", outcomes[0]?.committed === true);
  check("AC3 happy: step 2 committed", outcomes[1]?.committed === true);
  check("AC3 happy: step 2 staged with the created id", stagedWith === 101, String(stagedWith));
}

// --- AC3 atomicity: a LATE-step failure leaves step 1 committed and strands nothing
async function lateFailure() {
  let registerCommits = 0;
  const outcomes = await driveCompound({
    confirmRegister: async () => { registerCommits++; return { id: 102, name: "pulseras rojas" }; },
    stageAct: async () => { throw new Error("stock insert rejected: quantity invalid"); },
    confirmAct: async () => { throw new Error("should never be called after stage fails"); },
  });
  check("AC3 late-fail: step 1 still committed (intact)", outcomes[0]?.committed === true);
  check("AC3 late-fail: step 2 reported failed", outcomes[1]?.committed === false);
  check("AC3 late-fail: no partial stranded (step 1 committed exactly once, never rolled back)", registerCommits === 1);
  check("AC3 late-fail: the failure reason is surfaced", /quantity invalid/.test(outcomes[1]?.error ?? ""), outcomes[1]?.error);
}

// --- D-050 trust boundary: a model-supplied product id on a parser proposal is stripped
const dirtyStock = stripModelProductIds({ operationType: "ADD_STOCK", args: { productId: 999, productRef: "termos", quantity: 10 } });
check("strip drops a parser-supplied productId on stock", dirtyStock.args.productId === undefined && dirtyStock.args.productRef === "termos");
const dirtySale = stripModelProductIds({ operationType: "REGISTER_SALE", args: { items: [{ productId: 999, productRef: "medias", quantity: 2 }] } });
check("strip drops a parser-supplied productId on a sale item", (dirtySale.args.items as Array<Record<string, unknown>>)[0].productId === undefined && (dirtySale.args.items as Array<Record<string, unknown>>)[0].productRef === "medias");

// --- discriminated union (supports AC8's union; narrowing is sound)
const act = actionOf({ operationType: "ADD_STOCK", args: {} }, "llegaron 10 termos", "fallback");
check("union: an action narrows as action", isAction(act) && !isQuery(act));

await happy();
await lateFailure();

console.log(fails ? `\n${fails} FAILED` : "\nALL PASS");
process.exit(fails ? 1 : 0);
