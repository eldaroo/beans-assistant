// Named test for spec 009 M4 (AC8 QUERY kind off the write path, AC9 the ~15 owner reads).
// PURE: reads are injected fakes, so no DB. Run: npx tsx scripts/t-query.mts
//
// AC8's claim: "a QUERY never writes a row and never reaches /api/ops/confirm." Pinned
// two ways here: behaviorally (a write utterance dispatches to NO query, so it falls
// through to the write path) and structurally (query.ts imports no commit/stage/confirm
// surface at all). AC9: each of the 15 owner questions renders a Spanish answer from a
// read function called directly.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dispatchQuery, QUERY_REGISTRY, realReads, type Reads } from "@/lib/ops/query";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

// --- Injected read fakes. Every one is a READ: none registers, commits, cancels, or
//     mutates. A recorder proves dispatch only ever calls reads.
const called: string[] = [];
const rec = <T>(name: string, v: T) => { called.push(name); return v; };
const products = [
  { id: 1, sku: "med-az", name: "Medias Azules", unitCostCents: 100, unitPriceCents: 300, unitCostUsd: 1, unitPriceUsd: 3, isActive: true, description: null },
  { id: 2, sku: "ter-ro", name: "Termo Rojo", unitCostCents: 500, unitPriceCents: 1200, unitCostUsd: 5, unitPriceUsd: 12, isActive: true, description: null },
];
const completeCmp = (name: string) => ({
  productId: 1, productName: name,
  margins: [{ country: "Colombia", landed: { productId: 1, productName: name, country: "Colombia", components: [], totalCents: 5000, status: "completo", pendingLabels: [], isComplete: true }, priceCents: 9000, marginCents: 4000, pendingReason: null }],
  lowestCompleteCountry: "Colombia",
});
const fakeReads: Reads = {
  dashboardSnapshot: async () => rec("dashboardSnapshot", { revenueUsd: 48600, profitUsd: 12000, recentDays: [{ day: "2026-10-24", paid_sales_count: 14, paid_revenue_cents: 4860000, paid_revenue_usd: 48600 }] }),
  revenuePaidCents: async () => rec("revenuePaidCents", 4860000),
  profitUsd: async () => rec("profitUsd", 12000),
  salesSummary: async () => rec("salesSummary", []),
  currentStock: async () => rec("currentStock", [{ product_id: 1, sku: "med-az", name: "Medias Azules", stock_qty: 12 }, { product_id: 2, sku: "ter-ro", name: "Termo Rojo", stock_qty: 8 }]),
  listProducts: async () => rec("listProducts", products as never),
  expensesTotalCents: async () => rec("expensesTotalCents", 73500),
  directory: async () => rec("directory", [{ id: 1, name: "Acero SA", country: "Colombia", contact: null, isActive: true, lastCheckinAt: null, isOverdue: false, daysSinceCheckin: null }]),
  overdueCheckins: async () => rec("overdueCheckins", [{ id: 2, name: "Hilados Norte", country: "Peru", contact: null, isActive: true, lastCheckinAt: null, isOverdue: true, daysSinceCheckin: 20 }]),
  overdueArrivals: async () => rec("overdueArrivals", [{ country: "Colombia", periodWeek: "2026-W40", unitsProduced: 0, unitsTarget: 100, expectedNextAt: null, isOverdue: true, hasTarget: true, pctOfTarget: 0, meetsTarget: false }]),
  pendingCustoms: async () => rec("pendingCustoms", [{ country: "Costa Rica", shippingCents: null, customsCents: null, shippingNote: null, customsNote: null, isComplete: false, totalCents: null, pendingLabels: [], customsPending: true }]),
  countryComparison: async (_id: number) => rec("countryComparison", completeCmp("Medias Azules")),
  handleScenario: async (_m: string) => rec("handleScenario", "Escenario para Medias Azules en Colombia: costo final USD 50.00."),
};

// --- AC9: 15 owner questions, each to its expected read entry, each a Spanish string
const CASES: Array<[string, string]> = [
  ["que pasa si produzco en colombia?", "escenario_costos"],
  ["cuanto vendi hoy?", "ventas_hoy"],
  ["que atiendo hoy?", "atiendo_hoy"],
  ["que llegadas estan atrasadas?", "llegadas_atrasadas"],
  ["que tengo en aduana?", "aduana_pendiente"],
  ["que proveedores por contactar tengo?", "proveedores_atrasados"],
  ["que proveedores tengo?", "proveedores"],
  ["que stock me queda?", "stock_actual"],
  ["que productos tengo?", "catalogo"],
  ["cuanto gaste este mes?", "gastos"],
  ["cuanto gane en total?", "ganancia"],
  ["cuanto facture en total?", "facturacion"],
  ["donde conviene producir las medias?", "comparacion_paises"],
  ["cual es el margen de las medias?", "margen"],
  ["cuanto cuesta producir el termo?", "costo"],
];
check("AC9: 15 reads wired", CASES.length === 15 && QUERY_REGISTRY.length === 15, `cases=${CASES.length} registry=${QUERY_REGISTRY.length}`);
const seen = new Set<string>();
for (const [utterance, expectedId] of CASES) {
  const r = await dispatchQuery(utterance, fakeReads);
  const okId = r?.queryId === expectedId;
  const okReply = typeof r?.reply === "string" && r.reply.length > 0;
  check(`AC9 "${utterance}" -> ${expectedId}`, Boolean(okId && okReply), okId ? r!.reply : `got ${r?.queryId ?? "null"}`);
  if (r) seen.add(r.queryId);
}
check("AC9: every registry entry reachable by some utterance", seen.size === QUERY_REGISTRY.length, `${seen.size}/${QUERY_REGISTRY.length}`);

// --- AC8 behavioral: a WRITE utterance dispatches to NO query (falls through to write path)
for (const write of ["vendi 2 medias a 300", "gaste 500 en envio", "llegaron 10 termos", "cancela la venta 42"]) {
  const r = await dispatchQuery(write, fakeReads);
  check(`AC8 write "${write}" is NOT a query`, r === null, r ? `leaked to ${r.queryId}` : "");
}

// --- AC8 structural: query.ts imports no commit/stage/confirm/pending surface. Checked
//     against CODE with comments stripped, so the module's own doc comment ("never
//     reaches /api/ops/confirm") does not count as a reference.
const qsrcRaw = readFileSync(fileURLToPath(new URL("../lib/ops/query.ts", import.meta.url)), "utf8");
const qcode = qsrcRaw.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
const importSpecs = [...qcode.matchAll(/from\s+["']([^"']+)["']/g)].map((m) => m[1]);
for (const forbidden of ["pending-ops", "ops/registry", "ops/stage", "ops/confirm"]) {
  check(`AC8 query.ts imports no write module: ${forbidden}`, !importSpecs.some((s) => s.includes(forbidden)), importSpecs.join(","));
}
for (const forbidden of ["/api/ops/confirm", "markCommitted", "claim(", ".commit("]) {
  check(`AC8 query.ts code has no write call: ${forbidden}`, !qcode.includes(forbidden));
}

// --- AC8: dispatch only ever called read functions (recorder names are all reads)
const WRITE_WORDS = /register|create|cancel|add|update|commit|insert|delete|stage|undo/i;
check("AC8: only read functions were called", called.every((n) => !WRITE_WORDS.test(n)), called.filter((n) => WRITE_WORDS.test(n)).join(",") || "none");
check("AC8: realReads surface exposes only reads", Object.keys(realReads).every((k) => !WRITE_WORDS.test(k)), Object.keys(realReads).filter((k) => WRITE_WORDS.test(k)).join(",") || "none");

console.log(fails ? `\n${fails} FAILED` : "\nALL PASS");
process.exit(fails ? 1 : 0);
