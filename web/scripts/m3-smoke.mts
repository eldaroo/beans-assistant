// M3 integration smoke: the two-phase registry path (stage -> verdict -> confirm ->
// undo) exactly as the routes drive it, minus the HTTP/auth shell (covered by tsc +
// next build + a live 401 check). Runs against a live Neon branch.
import { getOp } from "@/lib/ops/registry";
import * as pending from "@/lib/pending-ops";
import { computeVerdict } from "@/lib/verdict";
import { createProduct } from "@/lib/domains/products";
import { addStock, stockForProduct } from "@/lib/domains/stock";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

async function stageOp(operationType: string, args: Record<string, unknown>, utterance: string) {
  const op = getOp(operationType)!;
  const resolved = await op.resolve(args);
  const opToken = crypto.randomUUID();
  await pending.stage({
    opToken, operationType, args: resolved.stagedArgs, utterance,
    productName: resolved.productName, candidateCount: resolved.candidateCount, turnNonce: crypto.randomUUID(),
  });
  const verdict = computeVerdict({
    operationType, utterance, groundedAmounts: resolved.groundedAmounts,
    productName: resolved.productName, candidateCount: resolved.candidateCount,
    withinCaps: true, irreversible: op.irreversible,
  });
  await pending.setVerdict(opToken, verdict);
  return { opToken, verdict };
}

async function confirmOp(opToken: string) {
  const po = (await pending.get(opToken))!;
  const op = getOp(po.operationType)!;
  const won = await pending.claim(opToken);
  if (!won) return { won: false, result: null as unknown };
  const result = await op.commit(po.args as Record<string, unknown>);
  await pending.markCommitted(opToken, result);
  return { won: true, result };
}

async function main() {
  const p = await createProduct({ sku: `OP-${Date.now()}`, name: "medias", unitCostCents: 0, unitPriceCents: 30000 });
  await addStock({ productId: p.id, quantity: 10 });
  const start = await stockForProduct(p.id);

  // Reversible, grounded, single-candidate sale -> AUTO.
  const staged = await stageOp("REGISTER_SALE", { items: [{ productId: p.id, quantity: 2 }] }, "vendi 2 medias");
  check("REGISTER_SALE grounded+single -> auto verdict", staged.verdict.auto === true, staged.verdict.reasons.join(","));

  const c = await confirmOp(staged.opToken);
  check("confirm commits (single winner)", c.won === true);
  check("stock down by 2 after sale", (await stockForProduct(p.id)) === start - 2);
  const c2 = await confirmOp(staged.opToken);
  check("second confirm does not re-commit (claim lost)", c2.won === false);

  // Undo path.
  const po = (await pending.get(staged.opToken))!;
  const op = getOp(po.operationType)!;
  const wonCancel = await pending.claimCancel(staged.opToken);
  await op.undo!(po.commitResult as Record<string, unknown>);
  await pending.finalizeCancelled(staged.opToken);
  check("undo claims + reverses stock", wonCancel === true && (await stockForProduct(p.id)) === start);

  // Irreversible op -> confirm card, never auto.
  const deact = await stageOp("DEACTIVATE_PRODUCT", { productId: p.id }, "dar de baja medias");
  check("DEACTIVATE_PRODUCT is never auto (irreversible)", deact.verdict.auto === false);

  // Ungrounded amount -> not auto.
  const ung = await stageOp("REGISTER_SALE", { items: [{ productId: p.id, quantity: 2, unitPriceCents: 99900 }] }, "vendi 2 medias");
  check("explicit price not in utterance -> not auto", ung.verdict.auto === false);

  console.log(fails === 0 ? "\nM3-SMOKE: ALL-PASS" : `\nM3-SMOKE: ${fails} FAIL`);
  process.exit(fails === 0 ? 0 : 1);
}

main().catch((e) => { console.error("SMOKE-ERROR", e); process.exit(2); });
