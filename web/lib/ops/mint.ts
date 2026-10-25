// Minting a minimal product from a name alone (spec 009 AC2 / D-047). When the owner
// says "me entraron 50 pulseras rojas" and "pulseras rojas" is not a known product, the
// app offers to create it in one step. That created product is MINIMAL on purpose: a
// derived sku, unit cost 0, price pending. The owner sets the real cost and price later
// (the cost-model guided flow, M7). Pure: no DB; the disambiguating suffix is injectable
// so the slug is fully deterministic in tests, while two same-named mints stay insertable.

// Slugify a Spanish product name into a sku stem: lowercase, strip accents, keep
// alphanumerics, collapse runs into single hyphens, trim, cap length.
export function deriveSkuStem(name: string): string {
  return (name || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/\p{Mn}/gu, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32);
}

// A 4-char base36 suffix so two products minted from the same name do not collide on the
// unique sku. Masking by 36**4 keeps the full 4-digit entropy (a wider value would lose its
// most-significant digit to padStart's width); a collision still fails cleanly on the sku
// unique constraint, this just makes one improbable.
const SUFFIX_SPACE = 36 ** 4; // 1_679_616
function suffix(): string {
  const n = Math.floor((globalThis.crypto?.getRandomValues?.(new Uint32Array(1))?.[0] ?? Math.random() * 0xffffffff));
  return (n % SUFFIX_SPACE).toString(36).padStart(4, "0");
}

export interface MinimalProductArgs {
  sku: string;
  name: string;
  unitCostCents: number;
  unitPriceCents: number | null;
  minted: true;
}

// Build the create-product args for a name-only mint. `unitPriceCents: null` is the
// "price pending" state the chat card surfaces; `unitCostCents: 0` is a placeholder the
// owner replaces via the cost flow. `minted` marks this as an app-minted minimal product
// so the chat card can say "precio pendiente, lo ponemos despues".
export function mintMinimalProductArgs(name: string, skuSuffix: string = suffix()): MinimalProductArgs {
  const stem = deriveSkuStem(name) || "producto";
  return {
    sku: `${stem}-${skuSuffix}`,
    // Cap the name so pathological operator text cannot overrun the column; 120 chars is
    // far longer than any real product name.
    name: name.trim().slice(0, 120),
    unitCostCents: 0,
    unitPriceCents: null,
    minted: true,
  };
}
