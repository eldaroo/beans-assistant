// M2 integration smoke: exercises the real business-logic modules against a live
// Neon branch (never prod). Run: DATABASE_URL=<branch> npx tsx scripts/m2-smoke.mts
import { computeVerdict } from "@/lib/verdict";
import { parseNumbers, numeralIsGrounded } from "@/lib/money";
import { listProducts, resolveActiveProduct } from "@/lib/domains/products";
import { addStock, stockForProduct } from "@/lib/domains/stock";
import { registerSale, cancelSale } from "@/lib/domains/sales";
import * as pending from "@/lib/pending-ops";
import { appendAudit, withinCaps } from "@/lib/audit";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

async function main() {
  // 1. Pure verdict (no DB): the security spine.
  const vAuto = computeVerdict({
    operationType: "REGISTER_SALE", utterance: "vendi 2 medias a 300",
    groundedAmounts: [300], productName: "medias", candidateCount: 1,
  });
  check("verdict auto when grounded+single+reversible", vAuto.auto === true, JSON.stringify(vAuto.reasons));
  const vBare = computeVerdict({
    operationType: "REGISTER_SALE", utterance: "ok",
    groundedAmounts: [300], productName: "medias", candidateCount: 1,
  });
  check("verdict NOT auto on bare confirmation", vBare.auto === false);
  const vUng = computeVerdict({
    operationType: "REGISTER_SALE", utterance: "vendi medias",
    groundedAmounts: [999], productName: "medias", candidateCount: 1,
  });
  check("verdict NOT auto on ungrounded numeral", vUng.auto === false);
  check("parseNumbers resolves thousands 1.500 -> 1500", parseNumbers("1.500")[0] === 1500);
  check("numeralIsGrounded 300 in '300'", numeralIsGrounded(300, parseNumbers("vendi a 300")));

  // 2. Reads against the branch (inherits prod data: 4 products).
  const prods = await listProducts();
  check("listProducts returns the migrated catalog", prods.length === 4, `n=${prods.length}`);
  const priced = prods.find((p) => p.unitPriceCents != null)!;
  const res = await resolveActiveProduct(priced.sku);
  check("resolveActiveProduct exact SKU -> single candidate", res.candidateCount === 1 && res.product?.id === priced.id);

  // 3. Stock + transactional sale + reverse.
  const before = await stockForProduct(priced.id);
  await addStock({ productId: priced.id, quantity: 10, reason: "smoke seed" });
  const afterAdd = await stockForProduct(priced.id);
  check("addStock raises on-hand by 10", afterAdd === before + 10, `${before}->${afterAdd}`);

  const sale = await registerSale({ items: [{ productId: priced.id, quantity: 3 }], status: "PAID" });
  const afterSale = await stockForProduct(priced.id);
  check("registerSale PAID lowers stock by qty", afterSale === afterAdd - 3, `${afterAdd}->${afterSale}`);
  check("registerSale returns a sale id + total", typeof sale.sale_id === "number" && sale.total_usd! > 0);

  await cancelSale(sale.sale_id);
  const afterCancel = await stockForProduct(priced.id);
  check("cancelSale restores the stock", afterCancel === afterAdd, `${afterSale}->${afterCancel}`);

  // 4. Two-phase pending-ops state machine.
  const token = `smoke-${Date.now()}`;
  await pending.stage({ opToken: token, operationType: "REGISTER_SALE", args: { x: 1 }, turnNonce: "t1" });
  await pending.setVerdict(token, { auto: true, requiresHumanReview: false, reasons: [] });
  const got = await pending.get(token);
  check("pending-ops stage+get round-trips args", got != null && (got!.args as { x: number }).x === 1);
  const claim1 = await pending.claim(token);
  const claim2 = await pending.claim(token);
  check("pending-ops claim is single-winner", claim1 === true && claim2 === false);
  const mc = await pending.markCommitted(token, { ok: true });
  check("pending-ops markCommitted on the claimer", mc === true);

  // 5. Audit append + caps.
  await appendAudit({ name: "register_sale", outcome: "ok", opToken: token });
  check("withinCaps true under the floor", (await withinCaps("register_sale")) === true);

  console.log(fails === 0 ? "\nM2-SMOKE: ALL-PASS" : `\nM2-SMOKE: ${fails} FAIL`);
  process.exit(fails === 0 ? 0 : 1);
}

main().catch((e) => { console.error("SMOKE-ERROR", e); process.exit(2); });
