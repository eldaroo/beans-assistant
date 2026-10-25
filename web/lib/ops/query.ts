// The read registry (spec 009 M4 / AC8 / AC9 / D-049).
//
// A QUERY is the read-only half of the Proposal union. It is dispatched BEFORE the write
// path: no stage, no verdict, no op_token, no /api/ops/confirm, no undo. This module has
// NO commit surface by construction -- it imports only domain READ functions and the
// read-only cost-scenario. A question can never write a row.
//
// Dispatch is deterministic Spanish keyword matching (the same posture as handleScenario,
// never an LLM call on the read path). Each entry calls a domain function DIRECTLY, not
// the GET route handler, and renders a short Spanish answer. The reads are injected so the
// matching + formatting is unit-testable without a database.

import { dashboardSnapshot, revenuePaidCents, profitUsd, salesSummary, type SalesSummaryRow } from "@/lib/domains/analytics";
import { currentStock, type StockCurrentRow } from "@/lib/domains/stock";
import { listProducts, type ProductView } from "@/lib/domains/products";
import { expensesTotalCents } from "@/lib/domains/expenses";
import { directory, overdueCheckins, type SupplierStatus } from "@/lib/domains/suppliers";
import { overdueArrivals, type ProductionStatus } from "@/lib/domains/production";
import { pendingCustoms, type LogisticsLane } from "@/lib/domains/logistics";
import { countryComparison, type CountryComparison } from "@/lib/domains/costing";
import { handleScenario } from "@/lib/domains/cost-scenario";

// The read surface the registry depends on. Injected (default: the real domains) so a
// test can drive every entry with fakes and assert no write path is ever touched.
export interface Reads {
  dashboardSnapshot: typeof dashboardSnapshot;
  revenuePaidCents: typeof revenuePaidCents;
  profitUsd: typeof profitUsd;
  salesSummary: typeof salesSummary;
  currentStock: typeof currentStock;
  listProducts: typeof listProducts;
  expensesTotalCents: typeof expensesTotalCents;
  directory: typeof directory;
  overdueCheckins: typeof overdueCheckins;
  overdueArrivals: typeof overdueArrivals;
  pendingCustoms: typeof pendingCustoms;
  countryComparison: typeof countryComparison;
  handleScenario: typeof handleScenario;
}

export const realReads: Reads = {
  dashboardSnapshot, revenuePaidCents, profitUsd, salesSummary, currentStock,
  listProducts, expensesTotalCents, directory, overdueCheckins, overdueArrivals,
  pendingCustoms, countryComparison, handleScenario,
};

// ------------------------------------------------------------------- formatting
function norm(s: string): string {
  return String(s || "").toLowerCase().normalize("NFKD").replace(/\p{Mn}/gu, "");
}
function money(usd: number | null | undefined): string {
  if (usd == null) return "s/d";
  return `$ ${Number(usd).toLocaleString("es-AR", { maximumFractionDigits: 2 })}`;
}
function joinList(xs: string[], max = 6): string {
  if (xs.length <= max) return xs.join(", ");
  return `${xs.slice(0, max).join(", ")} y ${xs.length - max} mas`;
}
// Pick the product the message names, matching a name token against the catalog. Null
// when the message names none (the caller then asks which product).
function matchProduct(message: string, products: ProductView[]): ProductView | null {
  const n = norm(message);
  for (const p of products) {
    const words = norm(p.name).split(/\s+/).filter((w) => w.length > 2);
    if (words.some((w) => n.includes(w))) return p;
  }
  return null;
}

// ------------------------------------------------------------------- the registry
export interface QueryEntry {
  id: string;
  // Pure matcher over the normalized message. First entry to match wins.
  match: (n: string) => boolean;
  // Runs the read and renders a Spanish answer, or null to fall through to the next
  // entry (e.g. a scenario with no recognizable country).
  run: (message: string, reads: Reads) => Promise<string | null>;
}

const has = (...subs: string[]) => (n: string) => subs.some((s) => n.includes(s));

// Order matters: specific intents (ventas de hoy, stock) before generic ones
// (facturacion, catalogo). Scenario sits first because its phrasings are distinct.
export const QUERY_REGISTRY: QueryEntry[] = [
  {
    id: "escenario_costos",
    match: has("escenario", "que pasa si", "si produzco", "si lo produzco", "si muevo", "cuanto costaria", "cuanto saldria", "y si lo hago en", "mover la produc"),
    run: (message, reads) => reads.handleScenario(message),
  },
  {
    id: "ventas_hoy",
    match: has("vendi hoy", "cuanto vendi hoy", "ventas de hoy", "ventas hoy", "facture hoy", "vendimos hoy"),
    async run(_m, reads) {
      const snap = await reads.dashboardSnapshot();
      const today: SalesSummaryRow | undefined = snap.recentDays[0];
      if (!today) return "Todavia no hay ventas registradas.";
      return `El dia ${today.day}: ${money(today.paid_revenue_usd)} en ${today.paid_sales_count} ${today.paid_sales_count === 1 ? "venta pagada" : "ventas pagadas"}.`;
    },
  },
  {
    id: "atiendo_hoy",
    match: has("que atiendo hoy", "que tengo que hacer hoy", "que hago hoy", "prioridades de hoy", "que me falta hoy", "que atender", "que tengo pendiente"),
    async run(_m, reads) {
      const [arrivals, checkins, customs] = await Promise.all([
        reads.overdueArrivals(), reads.overdueCheckins(), reads.pendingCustoms(),
      ]);
      const bits: string[] = [];
      if (arrivals.length) bits.push(`${arrivals.length} ${arrivals.length === 1 ? "llegada atrasada" : "llegadas atrasadas"}`);
      if (checkins.length) bits.push(`${checkins.length} ${checkins.length === 1 ? "proveedor por contactar" : "proveedores por contactar"}`);
      if (customs.length) bits.push(`${customs.length} en aduana`);
      return bits.length ? `Hoy tenes: ${joinList(bits)}.` : "Nada urgente hoy: sin llegadas atrasadas, proveedores al dia y aduana limpia.";
    },
  },
  {
    id: "llegadas_atrasadas",
    match: has("llegadas atrasadas", "llegadas estan atrasadas", "produccion atrasada", "que llegadas", "arribos atrasados", "que esta atrasado", "atrasos de produccion"),
    async run(_m, reads) {
      const rows: ProductionStatus[] = await reads.overdueArrivals();
      if (!rows.length) return "No hay llegadas atrasadas.";
      const names = rows.map((r) => `${r.country ?? "s/pais"} (${r.periodWeek})`);
      return `${rows.length} ${rows.length === 1 ? "llegada atrasada" : "llegadas atrasadas"}: ${joinList(names)}.`;
    },
  },
  {
    id: "aduana_pendiente",
    match: has("aduana", "customs", "tramites de aduana"),
    async run(_m, reads) {
      const lanes: LogisticsLane[] = await reads.pendingCustoms();
      if (!lanes.length) return "No hay tramites de aduana pendientes.";
      return `${lanes.length} ${lanes.length === 1 ? "tramite de aduana pendiente" : "tramites de aduana pendientes"}: ${joinList(lanes.map((l) => l.country))}.`;
    },
  },
  {
    id: "proveedores_atrasados",
    match: has("proveedores atrasados", "check-in", "checkin", "visitar proveedor", "proveedores por contactar", "a quien tengo que contactar", "proveedores por visitar"),
    async run(_m, reads) {
      const rows: SupplierStatus[] = await reads.overdueCheckins();
      if (!rows.length) return "Todos los proveedores estan al dia con los check-ins.";
      return `${rows.length} ${rows.length === 1 ? "proveedor" : "proveedores"} sin contactar hace mas de 14 dias: ${joinList(rows.map((s) => s.name))}.`;
    },
  },
  {
    id: "proveedores",
    match: has("que proveedores", "mis proveedores", "cuantos proveedores", "lista de proveedores", "proveedores tengo"),
    async run(_m, reads) {
      const rows: SupplierStatus[] = await reads.directory();
      if (!rows.length) return "Todavia no tenes proveedores cargados.";
      const names = rows.map((s) => (s.country ? `${s.name} (${s.country})` : s.name));
      return `Tenes ${rows.length} ${rows.length === 1 ? "proveedor activo" : "proveedores activos"}: ${joinList(names)}.`;
    },
  },
  {
    id: "stock_actual",
    match: has("que stock", "stock me queda", "cuanto stock", "inventario", "que tengo en stock", "stock actual", "cuanto me queda"),
    async run(_m, reads) {
      const rows: StockCurrentRow[] = await reads.currentStock();
      if (!rows.length) return "No hay stock cargado todavia.";
      const top = rows.map((r) => `${r.name} ${r.stock_qty}`);
      return `Stock actual (${rows.length} ${rows.length === 1 ? "producto" : "productos"}): ${joinList(top)}.`;
    },
  },
  {
    id: "catalogo",
    match: has("que productos", "catalogo", "lista de productos", "mis productos", "que vendo", "cuantos productos"),
    async run(_m, reads) {
      const rows = await reads.listProducts();
      if (!rows.length) return "Todavia no tenes productos cargados.";
      return `Tenes ${rows.length} ${rows.length === 1 ? "producto activo" : "productos activos"}: ${joinList(rows.map((p) => p.name))}.`;
    },
  },
  {
    id: "gastos",
    // Question phrasings only: the bare token "gastos" is deliberately NOT a trigger, so a
    // write like "registra los gastos de octubre: 5000 luz" is not swallowed as a read.
    match: has("cuanto gaste", "cuanto llevo gastado", "total de gastos", "mis gastos", "cuanto gastamos", "que gastos tengo", "cuanto gasto en"),
    async run(_m, reads) {
      const cents = await reads.expensesTotalCents();
      return `Gastos totales (netos de cancelaciones): ${money(cents / 100)}.`;
    },
  },
  {
    id: "ganancia",
    match: has("ganancia", "cuanto gane", "utilidad", "rentabilidad total", "profit", "cuanto gano en total"),
    async run(_m, reads) {
      const p = await reads.profitUsd();
      return `Ganancia (ventas pagadas menos gastos): ${money(p)}.`;
    },
  },
  {
    id: "facturacion",
    match: has("cuanto facture", "facturacion", "ingresos", "cuanto vendi en total", "revenue", "cuanto vendi"),
    async run(_m, reads) {
      const cents = await reads.revenuePaidCents();
      return `Facturacion total (ventas pagadas): ${money(cents / 100)}.`;
    },
  },
  {
    id: "comparacion_paises",
    match: has("donde conviene producir", "comparacion de paises", "en que pais", "donde es mas barato", "comparar paises", "que pais conviene"),
    async run(message, reads) {
      const products = await reads.listProducts();
      const p = matchProduct(message, products) ?? products[0];
      if (!p) return "Todavia no tenes productos para comparar.";
      const cmp: CountryComparison = await reads.countryComparison(p.id);
      if (!cmp.lowestCompleteCountry) return `Para ${cmp.productName} todavia no puedo comparar: faltan componentes de costo en los paises.`;
      return `Para ${cmp.productName} conviene producir en ${cmp.lowestCompleteCountry} (es el costo completo mas bajo de los paises cargados).`;
    },
  },
  {
    id: "margen",
    match: has("margen", "cuanto gano por", "rentabilidad de", "cuanto me deja"),
    async run(message, reads) {
      const products = await reads.listProducts();
      const p = matchProduct(message, products);
      if (!p) return "Decime de que producto queres el margen (por nombre).";
      const cmp: CountryComparison = await reads.countryComparison(p.id);
      const complete = cmp.margins.filter((m) => m.landed.isComplete && m.marginCents != null);
      if (!complete.length) return `Para ${cmp.productName} todavia no puedo calcular el margen: falta cargar precio o componentes de costo.`;
      const best = complete.reduce((a, b) => ((b.marginCents ?? 0) > (a.marginCents ?? 0) ? b : a));
      return `Margen de ${cmp.productName}: ${money((best.marginCents ?? 0) / 100)} por unidad produciendo en ${best.country}.`;
    },
  },
  {
    id: "costo",
    match: has("cuanto cuesta", "costo de", "costo final de", "cuanto me sale", "cuanto me cuesta producir", "landed"),
    async run(message, reads) {
      const products = await reads.listProducts();
      const p = matchProduct(message, products);
      if (!p) return "Decime de que producto queres el costo (por nombre).";
      const cmp: CountryComparison = await reads.countryComparison(p.id);
      const complete = cmp.margins.filter((m) => m.landed.isComplete);
      if (!complete.length) {
        const any = cmp.margins[0];
        return `El costo de ${cmp.productName} todavia es parcial${any ? ` (piso ${money(any.landed.totalCents / 100)})` : ""}: faltan componentes.`;
      }
      const cheapest = complete.reduce((a, b) => (b.landed.totalCents < a.landed.totalCents ? b : a));
      return `Costo final de ${cmp.productName}: ${money(cheapest.landed.totalCents / 100)} produciendo en ${cheapest.country}.`;
    },
  },
];

// Dispatch a message to the read registry. Returns a Spanish answer and the matched
// query id, or null when the message is not a known read (the caller then tries the
// write path). Never stages, verdicts, commits, or undoes.
export async function dispatchQuery(
  message: string,
  reads: Reads = realReads,
): Promise<{ queryId: string; reply: string } | null> {
  const n = norm(message);
  for (const entry of QUERY_REGISTRY) {
    if (!entry.match(n)) continue;
    const reply = await entry.run(message, reads);
    if (reply != null) return { queryId: entry.id, reply };
  }
  return null;
}
