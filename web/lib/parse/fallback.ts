// Local deterministic fallback parser (spec 008: "the local deterministic fallback
// parser"). Best-effort regex extraction for the common Spanish write intents so the
// chat keeps working when the Nomad parser is unavailable. Conservative: returns null
// when it cannot confidently extract, so the turn is handled as a question, never a
// wrong write. The real breadth lives in the LLM parser on Nomad (M6).
import { parseOne } from "@/lib/money";
import { actionOf, type Proposal } from "@/lib/parse/types";
import { expandSaleItems } from "@/lib/flow";

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

// M3 (spec 009 AC6): a product name for a price change or deactivation, stripped of the
// edit verbs and fillers. Separate from productRef's STOP (which carries the write verbs).
const REF_STOP = new Set([
  "de", "del", "la", "el", "los", "las", "un", "una", "a", "por", "en", "al", "lo", "mi", "su",
  "producto", "precio", "nuevo", "nueva", "cambia", "cambiar", "cambiale", "pone", "poner", "pone le",
  "ponele", "ajusta", "ajustar", "actualiza", "actualizar", "subi", "subir", "baja", "bajar",
  "desactiva", "desactivar", "discontinua", "discontinuar", "dar", "da", "elimina", "eliminar",
  "borra", "borrar", "saca", "sacar", "quita", "quitar",
]);
function cleanName(text: string): string {
  return norm(text)
    .replace(/[^\w\s]/g, " ")
    .replace(/\d[\d.,]*\d|\d/g, " ")
    .split(/\s+/)
    .filter((w) => w && !REF_STOP.has(w))
    .join(" ")
    .trim();
}

// The correction/edit verbs (cancel, annul, revert, delete, deactivate). A turn carrying
// one of these is a correction, never a fresh write, so it is matched BEFORE the sale /
// expense / stock intents (which would otherwise swallow "cancela la venta" on "venta").
const CANCEL_VERB = /\b(cancel[ao]|cancelar|cancelame|anul[ao]|anular|anulame|borr[ao]|borrar|borrame|elimin[ao]|eliminar|revert[io]|revertir|deshac[eo]|deshacer)\b/;
const DEACTIVATE_VERB = /\b(desactiv[ao]|desactivar|discontinu[ao]|discontinuar)\b|\bda(r)?\s+de\s+baja\b/;

export function fallbackParse(message: string): Proposal | null {
  const raw = message.trim();
  if (!raw) return null;
  const n = norm(raw);
  const nums = orderedNumbers(raw);

  // ------------------------------------------------------ M3: corrections & edits (AC6)
  // The parser emits a DESCRIPTOR only and NEVER a numeric id (AC4); the server resolves
  // the descriptor to an id (resolve-ref.ts) and mints it. Each of these stages a
  // confirm-only card with the full consequence; none auto-posts (AC7, enforced server-side).

  // UPDATE_PRICE: "cambia el precio de las medias a 500", "actualiza el precio del termo a 1200".
  if (/\bprecio\b/.test(n) && nums.length && !CANCEL_VERB.test(n)) {
    const priceMatch = raw.match(/(?:\ba\s+|\ben\s+|\$)\s*(\d[\d.,]*\d|\d)/i);
    const v = priceMatch ? parseOne(priceMatch[1]) : nums[nums.length - 1].value;
    let seg = raw.replace(/^.*?precio\s+(?:de\s+la\s+|de\s+las\s+|de\s+los\s+|de\s+el\s+|del\s+|de\s+)?/i, "");
    if (priceMatch) {
      const cut = seg.toLowerCase().lastIndexOf(priceMatch[0].toLowerCase().trimStart());
      if (cut > 0) seg = seg.slice(0, cut);
    }
    const ref = cleanName(seg);
    if (v !== null && ref) {
      return actionOf(
        { operationType: "UPDATE_PRICE", args: { productRef: ref, unitPriceCents: Math.round(v * 100) } },
        raw,
        "fallback",
      );
    }
  }

  // Cancel family: route by the entity noun the owner names. The descriptor is the whole
  // utterance; resolve-ref strips the verbs and nouns and keeps the discriminator.
  if (CANCEL_VERB.test(n)) {
    if (/\b(producto|articulo)\b/.test(n) && !/\b(venta|vendi|gasto|egreso|entrada|ingreso|movimiento)\b/.test(n)) {
      const ref = cleanName(raw.replace(CANCEL_VERB, " "));
      if (ref) return actionOf({ operationType: "DEACTIVATE_PRODUCT", args: { productRef: ref } }, raw, "fallback");
    }
    if (/\b(venta|vendi|vendid)/.test(n)) return actionOf({ operationType: "CANCEL_SALE", args: { saleRef: raw } }, raw, "fallback");
    if (/\b(gasto|egreso|gaste|pague)/.test(n)) return actionOf({ operationType: "CANCEL_EXPENSE", args: { expenseRef: raw } }, raw, "fallback");
    if (/\b(entrada|ingreso|movimiento|stock|entraron|llegaron|repuse)/.test(n)) return actionOf({ operationType: "CANCEL_STOCK", args: { movementRef: raw } }, raw, "fallback");
  }

  // DEACTIVATE_PRODUCT without a cancel verb: "desactiva las medias", "da de baja el termo".
  if (DEACTIVATE_VERB.test(n)) {
    const ref = cleanName(raw.replace(DEACTIVATE_VERB, " "));
    if (ref) return actionOf({ operationType: "DEACTIVATE_PRODUCT", args: { productRef: ref } }, raw, "fallback");
  }

  // ----------------------------------------- M6: orphan operational writes (spec 009 AC12)
  // Matched before the generic sale/stock/expense intents so a supplier or production turn
  // is not swallowed by them. Each proposes a DESCRIPTOR only; the server resolves ids and
  // stages a confirm-only card (the ops are irreversible: true, never auto-posted).

  // CREATE_SUPPLIER: "nuevo proveedor Acme", "agrega un proveedor Juan de China", "alta de proveedor X".
  if (/\bproveedor(es)?\b/.test(n) && /\b(nuevo|nueva|agrega|agregar|agregame|alta|crea|crear|registra|registrar|sum[ao]|sumar)\b/.test(n)) {
    // Cut everything up to and including "proveedor" (the verb + noun lead); the name is
    // what follows. Keep "de" here so a trailing "de <pais>" can be read as the country.
    let seg = raw.replace(/^.*\bproveedor(es)?\b/i, "").trim();
    // A trailing "de <country>" is the country, not the name.
    let country: string | undefined;
    const cm = seg.match(/\bde\s+([a-zÀ-ſ]+)\s*$/i);
    if (cm) { country = cm[1].trim(); seg = seg.slice(0, cm.index).trim(); }
    // Strip any leading determiner the name does not need ("un Juan" -> "Juan").
    const name = seg.replace(/^\s*(un|una|el|la|a|de|del)\b/i, "").replace(/[^\w\s]/g, " ").replace(/\s+/g, " ").trim();
    if (name) return actionOf({ operationType: "CREATE_SUPPLIER", args: country ? { name, country } : { name } }, raw, "fallback");
  }

  // RECORD_CHECKIN: "atendi al proveedor Acme", "me contesto Acme", "hable con el proveedor X", "seguimiento de X".
  if (/\b(atend[io]|contest[oó]|contestaron|respond[io]|respondieron|hable|hablamos|contact[eo]|contactamos|seguimiento|check[\s-]?in)\b/.test(n) && /\bproveedor(es)?\b|\bcon\b/.test(n)) {
    return actionOf({ operationType: "RECORD_CHECKIN", args: { supplierRef: raw } }, raw, "fallback");
  }

  // RECORD_PRODUCTION: "produje 100 termos", "fabrique 50 en colombia", "produccion de 200 esta semana".
  if (/\b(produj[eo]|produci|fabriqu[eé]|fabrico|produccion|fabricacion|arme|arm[eé]|ensamble)\b/.test(n)) {
    const units = nums.length ? Math.round(nums[0].value) : 0;
    if (units > 0) {
      const cm = raw.match(/\ben\s+([a-zÀ-ſ]+)\b/i);
      const country = cm ? cm[1].trim() : undefined;
      // Product ref: strip the production verbs, numbers, country, and fillers.
      let seg = norm(raw)
        .replace(/\b(produj[eo]|produci|fabriqu[eé]|fabrico|produccion|fabricacion|arme|arm[eé]|ensamble)\b/g, " ")
        .replace(/\d[\d.,]*\d|\d/g, " ")
        .replace(/\b(unidades|unidad|esta|semana|este|mes|en|de|del|la|el|los|las|un|una)\b/g, " ");
      if (country) seg = seg.replace(new RegExp(`\\b${country.toLowerCase()}\\b`, "g"), " ");
      const ref = seg.replace(/\s+/g, " ").trim();
      const args: Record<string, unknown> = { unitsProduced: units };
      if (country) args.country = country;
      if (ref) args.productRef = ref;
      return actionOf({ operationType: "RECORD_PRODUCTION", args }, raw, "fallback");
    }
  }

  // EDIT_PRODUCT (non-price): rename, re-sku, or correct unit cost. "precio" routes to
  // UPDATE_PRICE above, so this never handles a price change.
  if (!/\bprecio\b/.test(n)) {
    // Rename: "renombra las medias a medias premium", "cambiale el nombre al termo a termo grande".
    const rename = raw.match(/\b(?:renombra(?:r|me)?|cambia(?:le|r)?\s+el\s+nombre|pone(?:le)?\s+(?:de\s+)?nombre)\b(.*)$/i);
    if (rename) {
      const tail = rename[1];
      const am = tail.match(/^(.*?)\s+\ba\s+(.+)$/i);
      if (am) {
        const ref = cleanName(am[1]);
        const name = am[2].replace(/[^\w\s]/g, " ").replace(/\s+/g, " ").trim();
        if (ref && name) return actionOf({ operationType: "EDIT_PRODUCT", args: { productRef: ref, name } }, raw, "fallback");
      }
    }
    // SKU: "el sku de termos es TRM-01", "cambiale el sku a X".
    if (/\bsku\b/.test(n)) {
      const skuMatch = raw.match(/\bsku\b\s+(?:de\s+|del\s+|a\s+|es\s+)?(.*)$/i);
      if (skuMatch) {
        const after = skuMatch[1];
        const em = after.match(/^(.*?)\s+(?:es|a|=|:)\s+([A-Za-z0-9\-_]+)\s*$/i);
        if (em) {
          const ref = cleanName(em[1]);
          const sku = em[2].trim();
          if (ref && sku) return actionOf({ operationType: "EDIT_PRODUCT", args: { productRef: ref, sku } }, raw, "fallback");
        }
      }
    }
    // Unit cost: "el costo de medias es 50", "costo de termos 1200".
    if (/\bcosto\b/.test(n) && nums.length) {
      const cost = nums[nums.length - 1].value;
      let seg = raw.replace(/\bcosto\b/gi, " ");
      const cut = seg.search(/\b(es|a|=|:|\$)\s*\d/i);
      if (cut > 0) seg = seg.slice(0, cut);
      const ref = cleanName(seg);
      if (ref) return actionOf({ operationType: "EDIT_PRODUCT", args: { productRef: ref, unitCostCents: Math.round(cost * 100) } }, raw, "fallback");
    }
  }

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
    // Price: a number introduced by "a" or "por" or "$".
    let unitPriceCents: number | undefined;
    let priceStart = -1;
    const priceMatch = raw.match(/(?:\ba\s+|\bpor\s+|\$)\s*(\d[\d.,]*)/i);
    if (priceMatch) {
      priceStart = raw.indexOf(priceMatch[0]);
      const v = parseOne(priceMatch[1]);
      if (v !== null) unitPriceCents = Math.round(v * 100);
    }
    // Quantity: a numeral that appears BEFORE the price region — never the price itself.
    // "vendi medias a 300" and "vendi medias azules y grises a 5" have no leading count, so
    // the only numeral IS the price; quantity defaults to 1 (not the price). (council: Amelia)
    const qtyNum = nums.find((num) => priceStart < 0 || num.start < priceStart);
    const qty = qtyNum ? Math.round(qtyNum.value) : 1;
    // Product ref: strip verb + numbers + the price tail.
    const refSource = priceMatch ? raw.slice(0, raw.indexOf(priceMatch[0])) : raw;
    const region = refSource.replace(/\b(vend[io]|vendi|vendo|venta)\b/gi, " ");
    // Attribute expansion (spec 009 AC11): one utterance naming two variants that share a
    // base noun ("medias azules y grises a 5") expands into one item per variant. Returns
    // null when there is no conjunction, so the single-item path below runs unchanged.
    const expanded = expandSaleItems(region, qty, unitPriceCents);
    if (expanded) {
      return actionOf({ operationType: "REGISTER_SALE", args: { items: expanded } }, raw, "fallback");
    }
    const ref = productRef(region);
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
