// M7 resolution / disambiguation / NULL-price parity (spec 008 AC4), live against
// an ephemeral Neon branch (a copy of prod schema + data). These are the DB-backed
// halves of AC4 the pure suite cannot reach. The resolver's rule is byte-identical
// to the Python oracle (backend/services/ops_resolver.py): an exact case-insensitive
// SKU match wins as the single candidate; otherwise a name substring match over
// ACTIVE products is counted, and 0 or >1 is not deterministic. This smoke seeds a
// controlled set and asserts the TS resolver yields exactly those counts, that the
// ADD_STOCK disambiguation (>1 candidate) routes to a card, and that the NULL-price
// write is blocked (never recorded as price 0). Run via the branch runner:
//   node scripts/parity/neon-branch.mjs run scripts/m7-resolution-parity.mts
import { createProduct, getProduct, resolveActiveProduct } from "@/lib/domains/products";
import { addStock } from "@/lib/domains/stock";
import { registerSale } from "@/lib/domains/sales";
import { stageOperation } from "@/lib/ops/stage";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

async function main() {
  const N = `m7${Date.now().toString(36)}`;
  // Controlled, nonce-prefixed catalog so substring matches are deterministic and
  // never collide with the migrated prod catalog on the branch.
  const zeta = await createProduct({ sku: `${N}ZE`, name: `${N} zeta`, unitCostCents: 0, unitPriceCents: 50000 });
  await createProduct({ sku: `${N}A1`, name: `${N} alfa roja`, unitCostCents: 0, unitPriceCents: 30000 });
  await createProduct({ sku: `${N}A2`, name: `${N} alfa azul`, unitCostCents: 0, unitPriceCents: 30000 });
  const np = await createProduct({ sku: `${N}NP`, name: `${N} sin precio`, unitCostCents: 0, unitPriceCents: null });

  // 1. Exact SKU match, case-insensitive -> single candidate (the rule's exact arm).
  const bySkuLower = await resolveActiveProduct(`${N}ze`.toLowerCase());
  check("exact SKU (lowercased) -> 1 candidate", bySkuLower.candidateCount === 1 && bySkuLower.product?.id === zeta.id,
    `count=${bySkuLower.candidateCount}`);

  // 2. Name substring, single match -> single candidate.
  const byNameSingle = await resolveActiveProduct(`${N} zeta`);
  check("name substring single -> 1 candidate", byNameSingle.candidateCount === 1 && byNameSingle.product?.id === zeta.id,
    `count=${byNameSingle.candidateCount}`);

  // 3. Name substring, multiple matches -> count>1, product null (disambiguation).
  const byNameAmbig = await resolveActiveProduct(`${N} alfa`);
  check("name substring ambiguous -> >1 candidates, product null",
    byNameAmbig.candidateCount === 2 && byNameAmbig.product === null, `count=${byNameAmbig.candidateCount}`);

  // 4. No match -> 0 candidates.
  const byNone = await resolveActiveProduct(`${N} inexistente xyz`);
  check("no match -> 0 candidates", byNone.candidateCount === 0 && byNone.product === null, `count=${byNone.candidateCount}`);

  // 5. ADD_STOCK disambiguation through the full stage path: >1 candidate -> card.
  const ambigStage = await stageOperation({
    operationType: "ADD_STOCK",
    args: { productRef: `${N} alfa`, quantity: 3 },
    utterance: `llegaron 3 ${N} alfa`,
  });
  check("ADD_STOCK ambiguous -> staged not-auto (card)",
    ambigStage.ok === true && ambigStage.auto === false && ambigStage.candidate_count === 2,
    ambigStage.ok ? ambigStage.reasons.join(",") : (ambigStage as { message: string }).message);

  // 6. ADD_STOCK deterministic + grounded -> auto.
  const okStage = await stageOperation({
    operationType: "ADD_STOCK",
    args: { productRef: `${N} zeta`, quantity: 7 },
    utterance: `llegaron 7 ${N} zeta`,
  });
  check("ADD_STOCK grounded single -> staged auto",
    okStage.ok === true && okStage.auto === true,
    okStage.ok ? okStage.reasons.join(",") : (okStage as { message: string }).message);

  // 7. NULL-price render honesty: a product with no price shows pending, not 0.
  const npView = await getProduct(np.id);
  check("NULL-price product renders unitPriceUsd null (not 0)",
    npView.unitPriceCents === null && npView.unitPriceUsd === null, `price=${npView.unitPriceCents}`);

  // 8. NULL-price WRITE block: selling a no-price product with no explicit price is
  //    refused, never silently recorded at price 0. Give it stock first so the block
  //    is the price check, not the stock check.
  await addStock({ productId: np.id, quantity: 10 });
  let blocked = false;
  let msg = "";
  try {
    await registerSale({ items: [{ productId: np.id, quantity: 1 }] });
  } catch (e) {
    blocked = true;
    msg = (e as Error).message;
  }
  check("NULL-price sale blocked (never price 0)", blocked && /precio de venta/i.test(msg), msg);

  console.log(fails === 0 ? "\nM7-RESOLUTION: ALL-PASS" : `\nM7-RESOLUTION: ${fails} FAIL`);
  process.exit(fails === 0 ? 0 : 1);
}

main().catch((e) => { console.error("SMOKE-ERROR", e); process.exit(2); });
