// Server-side reference resolution (spec 009 M2 / AC4 / AC5 / D-050 / s-03 / s-04).
//
// The owner says "la ultima venta", "la venta de Juan", "el gasto de luz", "la entrada de
// termos". The parser emits that DESCRIPTOR verbatim and NEVER a numeric id (D-050): a
// hijacked parser that emitted `saleId` would otherwise cancel the WRONG sale. The server
// turns the descriptor into { candidateCount, id, candidates } here, mirroring
// resolveActiveProduct. 0 or more-than-1 is not deterministic: 0 is a clean not-found, and
// more-than-1 drives the disambiguation picker (AC5), each option carrying the
// server-resolved id.
//
// The matchers are PURE over injected rows so the resolution logic is unit-testable without
// a DB (scripts/t-resolve-ref.mts). The thin resolve* wrappers fetch recent rows then match.

import { listSales, type SaleRow } from "@/lib/domains/sales";
import { listExpenses, type ExpenseView } from "@/lib/domains/expenses";
import { recentStockMovements, type StockMovementRef } from "@/lib/domains/stock";

export interface RefCandidate {
  id: number;
  label: string; // human-readable, for the picker option and the confirm card
  detail?: string; // a second line (date, status) to tell near-duplicates apart
}

export interface RefResolution {
  candidateCount: number;
  id: number | null; // the single match, or null when 0 or more-than-1
  candidates: RefCandidate[]; // one when deterministic, many to disambiguate, none when 0
}

// ------------------------------------------------------------------ text helpers
function norm(s: string): string {
  return String(s || "").toLowerCase().normalize("NFKD").replace(/\p{Mn}/gu, "");
}
function money(cents: number | null | undefined): string {
  if (cents == null) return "s/d";
  return `$ ${(Number(cents) / 100).toLocaleString("es-AR", { maximumFractionDigits: 2 })}`;
}
// A bare or "latest" descriptor names no discriminator: "la ultima venta", "el ultimo
// gasto", "la venta" alone. It resolves to the most recent row.
function wantsLatest(n: string): boolean {
  return /\b(ultim[oa]s?|reciente|anterior|pasad[oa])\b/.test(n);
}
// Words carried by a cancel/edit descriptor that are NOT a discriminator: the intent verbs
// and the entity nouns and the fillers. What remains is the thing that tells rows apart
// (a customer name, an expense topic, a product name).
const STOP = new Set([
  "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas", "a", "por", "con",
  "y", "en", "al", "lo", "mi", "su", "esa", "ese", "esta", "este", "aquella",
  "ultima", "ultimo", "ultimas", "ultimos", "reciente", "recientes", "anterior", "pasada", "pasado",
  // intent verbs
  "cancela", "cancelar", "cancelame", "anula", "anular", "anulame", "borra", "borrar", "borrame",
  "elimina", "eliminar", "reverti", "revertir", "deshace", "deshacer", "sacar", "saca",
  // entity nouns
  "venta", "ventas", "gasto", "gastos", "egreso", "egresos", "movimiento", "movimientos",
  "entrada", "entradas", "ingreso", "ingresos", "stock", "compra", "numero", "nro",
]);
function discriminatorTokens(n: string): string[] {
  return n
    .replace(/[^\w\s#]/g, " ")
    .split(/\s+/)
    .filter((w) => w && !STOP.has(w) && !/^\d+$/.test(w));
}
// An explicit id the owner may name in words: "#12", "venta 12", "numero 7". This is the
// operator naming a row by its own number, resolved server-side -- it is NOT a model id.
function explicitNumber(descriptor: string): number | null {
  const m = descriptor.match(/#\s*(\d+)|(?:venta|gasto|egreso|movimiento|entrada|nro|numero|n°|num)\s*#?\s*(\d+)/i);
  if (!m) return null;
  const v = m[1] ?? m[2];
  return v ? Number(v) : null;
}
function resolutionOf(candidates: RefCandidate[]): RefResolution {
  return {
    candidateCount: candidates.length,
    id: candidates.length === 1 ? candidates[0].id : null,
    candidates,
  };
}

// ------------------------------------------------------------------ pure matchers
export function matchSales(descriptor: string, rows: SaleRow[]): RefResolution {
  const active = rows.filter((r) => r.status !== "CANCELLED");
  const n = norm(descriptor);
  const label = (r: SaleRow): RefCandidate => {
    const when = r.createdAt ? String(r.createdAt).slice(0, 10) : null;
    const status = r.status === "PAID" ? "pagada" : r.status.toLowerCase();
    return {
      id: r.id,
      label: `Venta #${r.id}${r.customerName ? ` de ${r.customerName}` : ""} por ${money(r.totalAmountCents)}`,
      detail: when ? `${status} · ${when}` : status,
    };
  };

  const num = explicitNumber(descriptor);
  if (num != null) return resolutionOf(active.filter((r) => r.id === num).map(label));

  const toks = discriminatorTokens(n);
  if (toks.length) {
    const hit = active.filter((r) => {
      const cust = norm(r.customerName ?? "");
      return toks.some((t) => cust.includes(t));
    });
    return resolutionOf(hit.map(label));
  }
  // Bare or "ultima": the most recent active sale (rows arrive newest-first).
  if (wantsLatest(n) || toks.length === 0) {
    return resolutionOf(active.slice(0, 1).map(label));
  }
  return resolutionOf([]);
}

export function matchExpenses(descriptor: string, rows: ExpenseView[]): RefResolution {
  // A CANCELACION row is a compensation, never a cancel target.
  const active = rows.filter((r) => r.category !== "CANCELACION");
  const n = norm(descriptor);
  const label = (r: ExpenseView): RefCandidate => ({
    id: r.id,
    label: `Gasto #${r.id}${r.description ? ` de ${r.description}` : ""} por ${money(r.amountCents)}`,
    detail: r.expenseDate ?? undefined,
  });

  const num = explicitNumber(descriptor);
  if (num != null) return resolutionOf(active.filter((r) => r.id === num).map(label));

  const toks = discriminatorTokens(n);
  if (toks.length) {
    const hit = active.filter((r) => {
      const hay = norm(`${r.description ?? ""} ${r.category ?? ""}`);
      return toks.some((t) => hay.includes(t));
    });
    return resolutionOf(hit.map(label));
  }
  if (wantsLatest(n) || toks.length === 0) {
    return resolutionOf(active.slice(0, 1).map(label));
  }
  return resolutionOf([]);
}

export function matchStockMovements(descriptor: string, rows: StockMovementRef[]): RefResolution {
  const n = norm(descriptor);
  const label = (r: StockMovementRef): RefCandidate => ({
    id: r.id,
    label: `Entrada #${r.id} de +${r.quantity} ${r.productName}`,
    detail: r.occurredAt ? String(r.occurredAt).slice(0, 10) : undefined,
  });

  const num = explicitNumber(descriptor);
  if (num != null) return resolutionOf(rows.filter((r) => r.id === num).map(label));

  const toks = discriminatorTokens(n);
  if (toks.length) {
    const hit = rows.filter((r) => {
      const name = norm(r.productName);
      return toks.some((t) => name.includes(t));
    });
    return resolutionOf(hit.map(label));
  }
  if (wantsLatest(n) || toks.length === 0) {
    return resolutionOf(rows.slice(0, 1).map(label));
  }
  return resolutionOf([]);
}

// ------------------------------------------------------------------ DB wrappers
// Injected reads default to the real domains so a test drives the pure matchers above with
// fakes and never touches a database.
export interface RefReads {
  listSales: typeof listSales;
  listExpenses: typeof listExpenses;
  recentStockMovements: typeof recentStockMovements;
}
export const realRefReads: RefReads = { listSales, listExpenses, recentStockMovements };

export async function resolveSale(descriptor: string, reads: RefReads = realRefReads): Promise<RefResolution> {
  if (!descriptor.trim()) return { candidateCount: 0, id: null, candidates: [] };
  return matchSales(descriptor, await reads.listSales({ limit: 50 }));
}
export async function resolveExpense(descriptor: string, reads: RefReads = realRefReads): Promise<RefResolution> {
  if (!descriptor.trim()) return { candidateCount: 0, id: null, candidates: [] };
  return matchExpenses(descriptor, await reads.listExpenses({ limit: 100 }));
}
export async function resolveStockMovement(descriptor: string, reads: RefReads = realRefReads): Promise<RefResolution> {
  if (!descriptor.trim()) return { candidateCount: 0, id: null, candidates: [] };
  return matchStockMovements(descriptor, await reads.recentStockMovements(50));
}
