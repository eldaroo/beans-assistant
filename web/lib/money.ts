// Money + numeral grounding. Ported from backend/services/write_verdict.py so the
// app re-derives every amount from the operator's own text and never trusts the
// model's arithmetic (spec 008, the wal-ledger "no number left behind" invariant).
//
// All money is integer cents. A numeral is "grounded" when it equals, to the cent,
// a number the operator actually typed this turn.

// A maximal run of digits with optional thousands/decimal separators.
const NUMBER_RE = /\d[\d.,]*\d|\d/g;

// Round half to EVEN (banker's rounding), matching Python's built-in `round()`.
// JS `Math.round` rounds half UP, which diverges from the Python oracle on exact
// half-cent cases (e.g. 62.5 -> 62 in Python but 63 in Math.round; 2.5 -> 2 vs 3).
// Every cents computation ported from a Python `round()` MUST use this so the app
// re-derives the same integer cents the incumbent produced (spec 008 AC4 parity).
export function roundHalfEven(x: number): number {
  const floor = Math.floor(x);
  const diff = x - floor;
  if (diff < 0.5) return floor;
  if (diff > 0.5) return floor + 1;
  return floor % 2 === 0 ? floor : floor + 1; // exactly .5 -> nearest even
}

function stripAccents(text: string): string {
  return (text || "").normalize("NFD").replace(/\p{Mn}/gu, "");
}

// Parse one numeral token to a number, resolving thousands vs decimal separators.
// Locale is ambiguous, so a heuristic (matches the Python exactly):
//  - both '.' and ',' present  -> the LAST one is the decimal point, rest are thousands
//  - one separator once with EXACTLY three trailing digits -> thousands (1.500 = 1500)
//    otherwise that single separator is a decimal point (1.5 = 1.5, 12.50 = 12.5)
//  - one separator more than once -> thousands (1.500.000 = 1500000)
//  - no separator -> the integer
export function parseOne(raw: string): number | null {
  const s = (raw ?? "").trim();
  if (!s) return null;
  const hasDot = s.includes(".");
  const hasComma = s.includes(",");
  const toNum = (v: string): number | null => {
    const n = Number(v);
    return Number.isNaN(n) ? null : n;
  };
  if (hasDot && hasComma) {
    const dec = Math.max(s.lastIndexOf("."), s.lastIndexOf(","));
    const intpart = s.slice(0, dec).replace(/[.,]/g, "");
    const frac = s.slice(dec + 1).replace(/[.,]/g, "");
    return toNum(`${intpart}.${frac}`);
  }
  if (hasDot || hasComma) {
    const sep = hasDot ? "." : ",";
    const occurrences = s.split(sep).length - 1;
    if (occurrences > 1) return toNum(s.split(sep).join(""));
    const [left, right] = s.split(sep);
    if (right.length === 3) return toNum(left + right); // grouping -> thousands
    return toNum(`${left}.${right}`); // decimal
  }
  return toNum(s);
}

// Every numeral in `text` parsed to its numeric value (thousands/decimal resolved).
export function parseNumbers(text: string): number[] {
  const out = new Set<number>();
  for (const m of (text || "").matchAll(NUMBER_RE)) {
    const v = parseOne(m[0]);
    if (v !== null) out.add(v);
  }
  return [...out];
}

// True iff `value` equals (to the cent) a numeral the operator actually said.
export function numeralIsGrounded(
  value: number | string | null | undefined,
  utteranceNumbers: Array<number | string>,
): boolean {
  if (value === null || value === undefined) return false;
  const fval = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(fval)) return false;
  const nums: number[] = [];
  for (const n of utteranceNumbers || []) {
    if (typeof n === "number") nums.push(n);
    else {
      const v = parseOne(String(n));
      if (v !== null) nums.push(v);
    }
  }
  return nums.some((n) => Math.abs(fval - n) < 0.005);
}

export function tokenSet(text: string): Set<string> {
  return new Set(stripAccents((text || "").toLowerCase()).split(/\s+/).filter(Boolean));
}

export { stripAccents };

// Display helpers. Money is stored as integer cents; USD is cents / 100.
export function centsToUsd(cents: number | null | undefined): number | null {
  if (cents === null || cents === undefined) return null;
  return Math.round(cents) / 100;
}

export function formatUsd(cents: number | null | undefined): string {
  const usd = centsToUsd(cents);
  if (usd === null) return "-";
  return usd.toLocaleString("en-US", { style: "currency", currency: "USD" });
}
