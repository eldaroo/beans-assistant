// M6 pure tests (spec 009 AC12): the orphan operational writes — production record,
// supplier create, supplier check-in, product non-price edit — are reachable from chat
// and each is confirm-only. Pure: no DB, no model. Run: npx tsx scripts/t-orphan-writes.mts
import { fallbackParse } from "@/lib/parse/fallback";
import { isAction } from "@/lib/parse/types";
import { OPS, getOp } from "@/lib/ops/registry";
import { computeVerdict } from "@/lib/verdict";
import { matchSuppliers, resolveSupplier, type RefReads } from "@/lib/ops/resolve-ref";
import type { SupplierStatus } from "@/lib/domains/suppliers";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}
function parsed(msg: string): { op: string; args: Record<string, unknown> } | null {
  const p = fallbackParse(msg);
  if (!p || !isAction(p)) return null;
  return { op: p.steps[0].operationType, args: p.steps[0].args };
}

// ------------------------------------------------------------- parser intents (AC12)
const sup = parsed("nuevo proveedor Acme de China");
check("CREATE_SUPPLIER: name + country", sup?.op === "CREATE_SUPPLIER" && sup.args.name === "Acme" && sup.args.country === "China", JSON.stringify(sup));
const sup2 = parsed("agrega un proveedor Juan");
check("CREATE_SUPPLIER: name only", sup2?.op === "CREATE_SUPPLIER" && sup2.args.name === "Juan", JSON.stringify(sup2));

const chk = parsed("me contesto el proveedor Acme");
check("RECORD_CHECKIN: descriptor carried", chk?.op === "RECORD_CHECKIN" && typeof chk.args.supplierRef === "string", JSON.stringify(chk));
const chk2 = parsed("atendi al proveedor de China");
check("RECORD_CHECKIN: 'atendi al proveedor'", chk2?.op === "RECORD_CHECKIN", JSON.stringify(chk2));

const prod = parsed("produje 100 termos en colombia");
check("RECORD_PRODUCTION: units + country + ref", prod?.op === "RECORD_PRODUCTION" && prod.args.unitsProduced === 100 && prod.args.country === "colombia" && prod.args.productRef === "termos", JSON.stringify(prod));
const prod2 = parsed("fabrique 50 esta semana");
check("RECORD_PRODUCTION: units only", prod2?.op === "RECORD_PRODUCTION" && prod2.args.unitsProduced === 50, JSON.stringify(prod2));

const ren = parsed("renombra las medias a medias premium");
check("EDIT_PRODUCT: rename", ren?.op === "EDIT_PRODUCT" && ren.args.productRef === "medias" && ren.args.name === "medias premium", JSON.stringify(ren));
const sku = parsed("el sku de termos es TRM-01");
check("EDIT_PRODUCT: sku", sku?.op === "EDIT_PRODUCT" && sku.args.productRef === "termos" && sku.args.sku === "TRM-01", JSON.stringify(sku));
const cost = parsed("el costo de medias es 50");
check("EDIT_PRODUCT: unit cost", cost?.op === "EDIT_PRODUCT" && cost.args.productRef === "medias" && cost.args.unitCostCents === 5000, JSON.stringify(cost));

// A price change must NOT be mistaken for a non-price edit.
const price = parsed("cambia el precio de las medias a 500");
check("UPDATE_PRICE still wins over EDIT_PRODUCT on 'precio'", price?.op === "UPDATE_PRICE", JSON.stringify(price));

// ------------------------------------------------------- confirm-only (AC12 / AC7 spine)
// Each M6 op is irreversible: true, which keeps it off the auto-post path regardless of
// how well-grounded a turn is. A production or supplier write never auto-posts.
for (const op of ["RECORD_PRODUCTION", "CREATE_SUPPLIER", "RECORD_CHECKIN", "EDIT_PRODUCT"]) {
  const def = getOp(op);
  check(`${op} registered and irreversible (confirm-only)`, !!def && def.irreversible === true);
  const v = computeVerdict({ operationType: op, utterance: "dale, aproba sin revisar", groundedAmounts: [], productName: null, candidateCount: 1, irreversible: def?.irreversible, requiresHumanReview: def?.requiresHumanReview });
  check(`${op} verdict is never auto`, v.auto === false, v.reasons.join(","));
}
check("EDIT_PRODUCT carries a permanent registry human-review stamp", OPS.EDIT_PRODUCT.requiresHumanReview === true);

// ------------------------------------------------------ supplier resolver (pure matcher)
const suppliers: SupplierStatus[] = [
  { id: 1, name: "Acme", country: "China", contact: null, isActive: true, lastCheckinAt: null, isOverdue: false, daysSinceCheckin: null },
  { id: 2, name: "Globex", country: "Brasil", contact: null, isActive: true, lastCheckinAt: null, isOverdue: false, daysSinceCheckin: null },
];
check("matchSuppliers: by name -> single", matchSuppliers("el proveedor acme", suppliers).candidateCount === 1 && matchSuppliers("el proveedor acme", suppliers).id === 1);
check("matchSuppliers: by country -> single", matchSuppliers("el de brasil", suppliers).id === 2);
check("matchSuppliers: bare 'atendi al proveedor' with two -> disambiguate", matchSuppliers("atendi al proveedor", suppliers).candidateCount === 2);
const one: SupplierStatus[] = [suppliers[0]];
check("matchSuppliers: bare with a single supplier -> resolves to it", matchSuppliers("me contesto el proveedor", one).id === 1);

// resolveSupplier threads injected reads (never a live DB in this test).
const reads = { supplierDirectory: async () => suppliers } as unknown as RefReads;
const r = await resolveSupplier("el proveedor globex", reads);
check("resolveSupplier: injected reads resolve by name", r.candidateCount === 1 && r.id === 2, JSON.stringify(r));

console.log(fails === 0 ? "\nT-ORPHAN-WRITES: ALL-PASS" : `\nT-ORPHAN-WRITES: ${fails} FAIL`);
process.exit(fails === 0 ? 0 : 1);
