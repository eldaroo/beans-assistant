// Local deterministic fallback parser (spec 008: "the local deterministic fallback
// parser"). Best-effort regex extraction for the common Spanish write intents so the
// chat keeps working when the Nomad parser is unavailable. Conservative: returns null
// when it cannot confidently extract, so the turn is handled as a question, never a
// wrong write. The real breadth lives in the LLM parser on Nomad (M6).
import { parseOne } from "@/lib/money";
import { actionOf, type Proposal } from "@/lib/parse/types";

function norm(s: string): string {
  return s.toLowerCase().normalize("NFKD").replace(/\p{Mn}/gu, "");
}

interface Num {
  value: number;
  start: number;
  end: number;
}

function orderedNumbers(s: string): Num[] {
  const out: Num[] = [];
  const re = /\d[\d.,]*\d|\d/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    const v = parseOne(m[0]);
    if (v !== null) out.push({ value: v, start: m.index, end: m.index + m[0].length });
  }
  return out;
}

// Words to strip from a product reference guess: fillers + the intent verbs.
const STOP = new Set([
  "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas", "a", "por",
  "con", "y", "en", "al", "lo", "mas", "pesos", "dolares", "usd", "stock", "unidades",
  "unidad", "cada",
  // intent verbs (so "llegaron termos" -> "termos")
  "llegaron", "llego", "entraron", "entro", "sume", "sumo", "agregue", "agrego",
  "repuse", "repon", "ingreso", "ingresaron", "vendi", "vendo", "venta", "vendio",
  "compre", "gaste", "gasto", "pague", "pago",
]);

function productRef(text: string): string {
  return norm(text)
    .replace(/[^\w\s]/g, " ")
    .replace(/\d[\d.,]*\d|\d/g, " ")
    .split(/\s+/)
    .filter((w) => w && !STOP.has(w))
    .join(" ")
    .trim();
}

export function fallbackParse(message: string): Proposal | null {
  const raw = message.trim();
  if (!raw) return null;
  const n = norm(raw);
  const nums = orderedNumbers(raw);

  // Expense: "gaste 500 en envio", "gasto de 500 en flete", "pague 200 de luz".
  if (/\b(gast[eo]|gaste|pagu[eo]|pague|egreso)\b/.test(n)) {
    if (!nums.length) return null;
    const amount = nums[0].value;
    const after = raw.slice(nums[0].end);
    const descMatch = after.match(/\b(?:en|de|por|para)\s+(.*)$/i);
    const description = (descMatch ? descMatch[1] : after).replace(/[^\w\s]/g, " ").trim() || "gasto";
    return actionOf(
      { operationType: "REGISTER_EXPENSE", args: { amountCents: Math.round(amount * 100), description } },
      raw,
      "fallback",
    );
  }

  // Stock in: "llegaron 10 termos", "entraron 20 medias", "sume 15 de stock de X".
  if (/\b(lleg[oa]ron|llego|entr[oa]ron|entro|sum[eo]|agregu[eo]|repon|repuse|ingreso)\b/.test(n) || /\bstock\b/.test(n)) {
    if (/\bvend|venta\b/.test(n)) {
      // "vendi" wins over a stray stock word; fall through to sale.
    } else {
      if (!nums.length) return null;
      const qty = Math.round(nums[0].value);
      const ref = productRef(raw);
      if (!ref) return null;
      return actionOf(
        { operationType: "ADD_STOCK", args: { productRef: ref, quantity: qty } },
        raw,
        "fallback",
      );
    }
  }

  // Sale: "vendi 2 medias a 300", "venta de 3 termos", "vendi medias a 300".
  if (/\b(vend[io]|vendi|vendo|venta)\b/.test(n)) {
    const qty = nums.length ? Math.round(nums[0].value) : 1;
    // Price: a number introduced by "a" or "por" or "$".
    let unitPriceCents: number | undefined;
    const priceMatch = raw.match(/(?:\ba\s+|\bpor\s+|\$)\s*(\d[\d.,]*)/i);
    if (priceMatch) {
      const v = parseOne(priceMatch[1]);
      if (v !== null) unitPriceCents = Math.round(v * 100);
    }
    // Product ref: strip verb + numbers + the price tail.
    const refSource = priceMatch ? raw.slice(0, raw.indexOf(priceMatch[0])) : raw;
    const ref = productRef(refSource.replace(/\b(vend[io]|vendi|vendo|venta)\b/gi, " "));
    if (!ref) return null;
    const item: Record<string, unknown> = { productRef: ref, quantity: qty };
    if (unitPriceCents !== undefined) item.unitPriceCents = unitPriceCents;
    return actionOf(
      { operationType: "REGISTER_SALE", args: { items: [item] } },
      raw,
      "fallback",
    );
  }

  return null;
}
