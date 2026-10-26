// Multi-turn flow helpers (spec 009 M5, AC11). Pure: no DB, no model, no network, so
// the flow logic is provable without a live branch. Two capabilities live here:
//
//   1. Price completion. "vendi 40 stanleys" names a sale with no price, so the app asks
//      "a que precio?"; the operator answers "32"; the app completes the sale with that
//      price. Both numerals (40 from the first turn, 32 from the answer) must ground, so
//      grounding runs against the flow's recorded operator turns (lib/flow-turns.ts), not
//      a single utterance. These helpers detect the "needs price" state and the price
//      answer; the chat route stitches them to the server-authenticated turn record.
//
//   2. Attribute expansion. "medias azules y grises a 5" is one utterance naming two
//      product variants that share a base noun; it expands into two sale item steps,
//      "medias azules" and "medias grises", each its own item. The step stays the unit of
//      commit (D-047): the parser proposes the expanded items, the app resolves and
//      verdicts each the same way it would a single item.

import { parseOne, stripAccents, roundHalfEven } from "@/lib/money";
import type { ParsedOp } from "@/lib/parse/types";

type SaleItem = { productId?: number; productRef?: string; quantity: number; unitPriceCents?: number };

// A lone price answer in a flow: the operator replied with just a number (optionally
// "$", "a", "por", "pesos"), nothing else. Returns the value in major units, or null.
// A turn that also names a product or a verb is NOT a bare answer — it starts a new op.
// The separators '.' and ',' are kept inside number tokens so "1.500" parses as 1500.
const PRICE_ANSWER_STOP = new Set(["a", "por", "de", "cada", "uno", "c", "u", "pesos", "peso", "mango", "mangos", "lucas", "luca"]);
export function priceAnswer(message: string): number | null {
  const n = stripAccents((message || "").toLowerCase()).replace(/\$/g, " ").replace(/[^\w\s.,]/g, " ").replace(/\s+/g, " ").trim();
  if (!n) return null;
  const words = n.split(" ").filter(Boolean);
  let value: number | null = null;
  for (const w of words) {
    if (/^\d[\d.,]*\d$|^\d$/.test(w)) {
      if (value !== null) return null; // more than one number -> not a lone price answer
      value = parseOne(w);
    } else if (!PRICE_ANSWER_STOP.has(w)) {
      return null; // a non-filler word -> this is not a bare price answer
    }
  }
  return value;
}

// True iff the op is a REGISTER_SALE with at least one item that still has no price. A
// sale cannot post without a price, so the app asks for it rather than staging a blank.
export function needsSalePrice(op: ParsedOp | null | undefined): boolean {
  if (!op || op.operationType?.toUpperCase?.() !== "REGISTER_SALE") return false;
  const items = (op.args?.items as SaleItem[] | undefined) ?? [];
  if (!items.length) return false;
  return items.some((it) => it.unitPriceCents == null);
}

// Fill a price (major units) into every price-less item of a sale op, returning a new op.
// Used to complete a pending sale from a lone price answer.
export function applySalePrice(op: ParsedOp, priceMajor: number): ParsedOp {
  // Banker's rounding to integer cents, matching lib/money (the "no number left behind"
  // parity invariant), so a completed price never diverges by a cent from the spine.
  const cents = roundHalfEven(priceMajor * 100);
  const items = ((op.args?.items as SaleItem[] | undefined) ?? []).map((it) =>
    it.unitPriceCents == null ? { ...it, unitPriceCents: cents } : it,
  );
  return { operationType: op.operationType, args: { ...op.args, items } };
}

// Attribute expansion core (AC11). Given the product region of a sale utterance (the text
// after the verb+quantity and before the price), split a shared-noun variant list into one
// ref per variant. "medias azules y grises" -> ["medias azules", "medias grises"]. Returns
// [] when there is no conjunction to expand, so the caller keeps its single-item path.
export function expandProductRegion(region: string): string[] {
  // Keep commas (variant separators) AND digits through the first normalization, so a
  // per-segment quantity can be DETECTED before it is stripped.
  const normed = stripAccents((region || "").toLowerCase())
    .replace(/[^\w\s,]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!normed) return [];
  // Split on "y" / "e" / commas as variant separators.
  const rawSegments = normed
    .split(/\s*,\s*|\s+y\s+|\s+e\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (rawSegments.length < 2) return [];
  // Conservative guard (council: Amelia): a numeral on a NON-FIRST segment means a
  // multi-quantity / multi-noun list ("2 medias y 3 termos"), not a shared-noun variant
  // list — folding would drop the per-segment counts, so bail to the single-item path. A
  // numeral on the FIRST segment is only a shared leading COUNT ("5 medias azules y grises"
  // = 5 of each variant); the count is captured separately by the caller, so strip it here
  // and still expand rather than killing the variant split.
  if (rawSegments.slice(1).some((s) => /\d/.test(s))) return [];
  const segments = rawSegments
    .map((s) => s.replace(/\b\d[\d.,]*\d\b|\b\d\b/g, " ").replace(/\s+/g, " ").trim())
    .filter(Boolean);
  if (segments.length < 2) return [];
  const baseNoun = segments[0].split(" ")[0]; // the shared product noun, e.g. "medias"
  if (!baseNoun) return [];
  const refs: string[] = [];
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    if (i === 0) {
      refs.push(seg);
      continue;
    }
    const segTokens = seg.split(" ");
    // A later segment that is a bare attribute (1-2 words) and does not already carry the
    // base noun inherits it: "grises" -> "medias grises". A segment that names its own
    // noun (already contains the base, or is long) is taken as written.
    if (segTokens.length <= 2 && !segTokens.includes(baseNoun)) {
      refs.push(`${baseNoun} ${seg}`.trim());
    } else {
      refs.push(seg);
    }
  }
  return refs;
}

// Build sale items from an expanded product region. Returns null when the region does not
// expand (no conjunction), so the caller keeps its existing single-item construction.
export function expandSaleItems(
  region: string,
  quantity: number,
  unitPriceCents?: number,
): SaleItem[] | null {
  const refs = expandProductRegion(region);
  if (refs.length < 2) return null;
  return refs.map((productRef) => {
    const it: SaleItem = { productRef, quantity };
    if (unitPriceCents !== undefined) it.unitPriceCents = unitPriceCents;
    return it;
  });
}
