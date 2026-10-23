// M5 integration smoke: the chat path (fallback parse + cost scenario + stage) as the
// chat route drives it, minus the HTTP/auth shell. Runs against a live Neon branch.
import { fallbackParse } from "@/lib/parse/fallback";
import { handleScenario } from "@/lib/domains/cost-scenario";
import { stageOperation } from "@/lib/ops/stage";
import { createProduct } from "@/lib/domains/products";
import { addStock } from "@/lib/domains/stock";
import * as cost from "@/lib/domains/costing";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

async function main() {
  // 1. Deterministic fallback parser (pure).
  const sale = fallbackParse("vendi 2 medias a 300");
  const si = (sale?.args.items as Array<Record<string, unknown>>)?.[0];
  check("parse sale: op+qty+ref+price", sale?.operationType === "REGISTER_SALE" && si?.quantity === 2 && si?.productRef === "medias" && si?.unitPriceCents === 30000, JSON.stringify(sale?.args));
  const exp = fallbackParse("gaste 500 en envio");
  check("parse expense: amount+desc", exp?.operationType === "REGISTER_EXPENSE" && exp?.args.amountCents === 50000 && String(exp?.args.description).includes("envio"), JSON.stringify(exp?.args));
  const stk = fallbackParse("llegaron 10 termos");
  check("parse stock: ref+qty", stk?.operationType === "ADD_STOCK" && stk?.args.productRef === "termos" && stk?.args.quantity === 10, JSON.stringify(stk?.args));
  check("parse non-op -> null", fallbackParse("hola como estas") === null);

  // 2. Parse -> stage -> verdict against the DB (the chat route's write path).
  // Use a name that does not collide with the migrated catalog, so the resolver
  // finds exactly one active candidate and the grounded sale can auto-post.
  await createProduct({ sku: `M5-${Date.now()}`, name: "kombucha", unitCostCents: 0, unitPriceCents: 30000 });
  const proposal = fallbackParse("vendi 2 kombucha a 300")!;
  const staged = await stageOperation({ operationType: proposal.operationType, args: proposal.args, utterance: proposal.utterance });
  check("stage parsed sale -> ok", staged.ok === true);
  if (staged.ok) check("parsed grounded single-candidate sale -> auto", staged.auto === true, staged.reasons.join(","));

  // 3. Read-only cost scenario.
  const p = await createProduct({ sku: `M5C-${Date.now()}`, name: "pulsera scenario", unitCostCents: 0, unitPriceCents: 1000 });
  const ci = await cost.recordCostInput("hilo", "hilo");
  await cost.recordInputPurchase({ costInputId: ci, originalCurrency: "USD", originalAmountCents: 50, fxRate: 1, quantity: 1 });
  await cost.recordBomLine(p.id, ci, "Colombia", 2);
  const reply = await handleScenario("cuanto costaria producir la pulsera en colombia");
  check("cost scenario returns a read-only reply", typeof reply === "string" && reply!.startsWith("Escenario") && reply!.includes("no cambié nada"), (reply ?? "").slice(0, 60));
  check("non-scenario message -> null (normal pipeline)", (await handleScenario("vendi 2 medias")) === null);

  console.log(fails === 0 ? "\nM5-SMOKE: ALL-PASS" : `\nM5-SMOKE: ${fails} FAIL`);
  process.exit(fails === 0 ? 0 : 1);
}

main().catch((e) => { console.error("SMOKE-ERROR", e); process.exit(2); });
