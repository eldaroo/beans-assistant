// Named test for spec 009 M2 (AC4 server-side reference resolution + no model id, AC5
// disambiguation). PURE: no DB, no network. Run: npx tsx scripts/t-resolve-ref.mts
//
// AC4's load-bearing claim is the trust boundary: the parser emits a DESCRIPTOR and never
// a numeric id, so a caller-supplied id cannot target an arbitrary row. stripModelIds is
// that boundary (it drops sale/expense/stock/product ids off a parser proposal), and the
// matchers resolve the descriptor server-side. AC5: more than one match yields a picker.
import { stripModelIds, stripModelProductIds, pickedStageArgs } from "@/lib/ops/compound";
import { matchSales, matchExpenses, matchStockMovements } from "@/lib/ops/resolve-ref";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

// ---- fake rows (shape matches the domain row types the real resolvers fetch) ----
const sale = (id: number, customerName: string | null, status = "PAID", totalAmountCents = 50000) =>
  ({ id, saleNumber: `S-${id}`, customerName, status, currency: "USD", totalAmountCents, createdAt: "2026-10-24T10:00:00Z", paidAt: null }) as never;
const expense = (id: number, description: string, category = "GENERAL", amountCents = 120000) =>
  ({ id, expenseDate: "2026-10-24", category, description, amountCents, currency: "USD", createdAt: "x", amountUsd: amountCents / 100 }) as never;
const mov = (id: number, productName: string, quantity = 10, movementType = "IN") =>
  ({ id, productId: id * 10, productName, movementType, quantity, occurredAt: "2026-10-24T10:00:00Z" }) as never;

// ---- AC4: stripModelIds drops EVERY model-supplied id (the trust boundary) ----
const dirtyCancel = stripModelIds({ operationType: "CANCEL_SALE", args: { saleId: 999, saleRef: "la ultima venta" } });
check("AC4 strip drops a model-supplied saleId", dirtyCancel.args.saleId === undefined, JSON.stringify(dirtyCancel.args));
check("AC4 strip keeps the descriptor", dirtyCancel.args.saleRef === "la ultima venta");
check("AC4 strip drops a model-supplied expenseId", stripModelIds({ operationType: "CANCEL_EXPENSE", args: { expenseId: 7 } }).args.expenseId === undefined);
check("AC4 strip drops a model-supplied movementId", stripModelIds({ operationType: "CANCEL_STOCK", args: { movementId: 5 } }).args.movementId === undefined);
check("AC4 strip still drops productId (superset of stripModelProductIds)", stripModelIds({ operationType: "DEACTIVATE_PRODUCT", args: { productId: 3, productRef: "medias" } }).args.productId === undefined);
check("stripModelProductIds unchanged (C1 contract intact)", stripModelProductIds({ operationType: "ADD_STOCK", args: { productId: 3, productRef: "x", quantity: 1 } }).args.productId === undefined);

// ---- AC4: a caller-supplied id cannot pick a row; only the descriptor resolves it ----
// "la venta de Juan" resolves to Juan's real sale (id 12), never to a model-named 999.
const salesRows = [sale(20, "Pedro"), sale(12, "Juan"), sale(5, "Ana")];
const juan = matchSales("cancelar la venta de Juan", salesRows);
check("AC4 descriptor resolves to the real id, not a model id", juan.candidateCount === 1 && juan.id === 12, JSON.stringify(juan));

// ---- AC5: more than one match returns a picker (candidateCount > 1, id null) ----
const twoJuans = matchSales("la venta de Juan", [sale(30, "Juan Perez"), sale(31, "Juan Lopez"), sale(32, "Marta")]);
check("AC5 two matches -> picker", twoJuans.candidateCount === 2 && twoJuans.id === null, JSON.stringify(twoJuans));
check("AC5 each option carries the server id", twoJuans.candidates.every((c) => typeof c.id === "number" && c.label.length > 0));

// ---- resolver precedence: latest, by name, by explicit number ----
const latest = matchSales("cancelar la ultima venta", salesRows);
check("latest resolves to the newest row (first in desc list)", latest.candidateCount === 1 && latest.id === 20);
const byNumber = matchSales("anular la venta #12", salesRows);
check("explicit number resolves by id", byNumber.candidateCount === 1 && byNumber.id === 12);
const cancelled = matchSales("la venta de Juan", [{ ...(sale(12, "Juan", "CANCELLED") as object) } as never]);
check("an already-cancelled sale is not a cancel target", cancelled.candidateCount === 0);

// ---- expenses: descriptor by topic, CANCELACION excluded ----
const expRows = [expense(9, "luz"), expense(8, "envio"), expense(7, "Cancelacion de #3: luz", "CANCELACION")];
const luz = matchExpenses("cancelar el gasto de luz", expRows);
check("expense resolves by description topic", luz.candidateCount === 1 && luz.id === 9, JSON.stringify(luz));
const ultimoGasto = matchExpenses("borra el ultimo gasto", expRows);
check("expense latest skips the CANCELACION row", ultimoGasto.id === 9);

// ---- stock movements: by product name, only IN/ADJUSTMENT reach the resolver ----
const movRows = [mov(1, "termos"), mov(2, "medias")];
const termos = matchStockMovements("revertir la entrada de termos", movRows);
check("stock movement resolves by product name", termos.candidateCount === 1 && termos.id === 1, JSON.stringify(termos));
const ambiguousMov = matchStockMovements("la entrada", movRows);
check("a bare 'la entrada' resolves to the latest movement", ambiguousMov.candidateCount === 1 && ambiguousMov.id === 1);

// ---- AC5 regression (council BLOCK): a disambiguation pick must NOT drop the non-id args
// it is changing. UPDATE_PRICE carries unitPriceCents through the pick; dropping it would
// re-stage a no-op and still report success. CANCEL_* carry only the id. ----
const priceMerged = pickedStageArgs({ unitPriceCents: 50000 }, "productId", 12);
check("AC5 pick keeps the new price AND sets the chosen id", priceMerged.unitPriceCents === 50000 && priceMerged.productId === 12, JSON.stringify(priceMerged));
const cancelMerged = pickedStageArgs({}, "saleId", 7);
check("AC5 cancel pick sets only the id", cancelMerged.saleId === 7 && Object.keys(cancelMerged).length === 1);

console.log(fails ? `\n${fails} FAILED` : "\nALL PASS");
process.exit(fails ? 1 : 0);
