// Named test for spec 010 M3 T-013/T-014 (D-059/D-061, AC5): the internal write-preview mapping
// and the GROUNDING KEYSTONE. PURE: no DB, no network. Run: npx tsx scripts/t-internal-preview.mts
//
// The kill risk this cohort closes: in the native tool-use loop the model proposes write args, so
// a tool-sourced or model-invented numeral must NOT auto-post. The defense is that the verdict
// grounds against the operator's OWN recorded words (operator_turns), never the model's tool args.
// This proves it three ways:
//   1. mapPreviewTool is a pure args -> op-args transform and NEVER emits an utterance or a
//      grounding corpus (so no tool arg can be lifted into the grounding source).
//   2. computeVerdict fed the operator corpus rejects an invented price absent from it (auto:false,
//      ungrounded-numerals) and accepts the grounded, deterministic, reversible write (auto:true).
//   3. The preview route sources its grounding from flow-turns (operator_turns), not the request
//      body (asserted against the route source so the wiring cannot silently regress).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { mapPreviewTool } from "@/lib/internal/preview-map";
import { computeVerdict } from "@/lib/verdict";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

const here = dirname(fileURLToPath(import.meta.url));

function main() {
  // --- 1. the pure mapping: register_sale -> REGISTER_SALE { items: [{ productRef, quantity, unitPriceCents }] }
  const m = mapPreviewTool("register_sale", { product: "medias", quantity: 2, unit_amount: 300 });
  check("register_sale maps to REGISTER_SALE", m.ok && m.input.operationType === "REGISTER_SALE", JSON.stringify(m));
  if (m.ok) {
    const items = (m.input.args as { items: Array<Record<string, unknown>> }).items;
    check("one item, productRef+quantity+unitPriceCents (whole units -> cents)",
      items.length === 1 && items[0].productRef === "medias" && items[0].quantity === 2 && items[0].unitPriceCents === 30000,
      JSON.stringify(items));
    // THE KEYSTONE, structurally: the mapping output has NO utterance / grounding field. There is
    // no key through which a tool arg could become the grounding source.
    const keys = Object.keys(m.input);
    check("map output is only {operationType, args} — no utterance/corpus key",
      keys.length === 2 && keys.includes("operationType") && keys.includes("args"),
      JSON.stringify(keys));
  }

  // --- quantity defaults to 1; a price-less sale stages without unitPriceCents
  const m1 = mapPreviewTool("register_sale", { product: "termo" });
  check("quantity defaults to 1, price-less stages no unitPriceCents",
    m1.ok && (m1.input.args as { items: Array<Record<string, unknown>> }).items[0].quantity === 1 && !("unitPriceCents" in (m1.input.args as { items: Array<Record<string, unknown>> }).items[0]),
    JSON.stringify(m1));

  // --- hardening (council: Amelia): a stringified/float quantity coerces to the real count
  // (matching the parser), and a negative price never stages (stages price-less instead)
  const mq = mapPreviewTool("register_sale", { product: "medias", quantity: "3", unit_amount: 300 });
  check("stringified quantity '3' coerces to 3 (not default 1)",
    mq.ok && (mq.input.args as { items: Array<Record<string, unknown>> }).items[0].quantity === 3, JSON.stringify(mq));
  const mneg = mapPreviewTool("register_sale", { product: "medias", quantity: 2, unit_amount: -50 });
  check("negative unit_amount stages price-less (no unitPriceCents)",
    mneg.ok && !("unitPriceCents" in (mneg.input.args as { items: Array<Record<string, unknown>> }).items[0]), JSON.stringify(mneg));

  // --- an unwired tool is a clean error, never a silent no-op (M4/M5 extend the map)
  const mu = mapPreviewTool("register_expense", { amount: 500, description: "envio" });
  check("unwired tool -> unsupported_tool error", !mu.ok && mu.code === "unsupported_tool", JSON.stringify(mu));
  const mb = mapPreviewTool("register_sale", {});
  check("register_sale without a product -> bad_tool_args", !mb.ok && mb.code === "bad_tool_args", JSON.stringify(mb));

  // --- 2. THE KEYSTONE, behaviorally (AC5). The operator typed "vendi 2 medias a 300". The model
  // calls register_sale but its args carry an INVENTED price of 999 (absent from what the operator
  // said). The verdict grounds the staged numerals [2, 999] against the operator corpus, so 999 is
  // ungrounded -> auto:false -> confirm card. This is the exact invented-numeral attack.
  const corpus = "vendi 2 medias a 300";
  const invented = computeVerdict({
    operationType: "REGISTER_SALE",
    utterance: corpus,
    groundedAmounts: [2, 999], // what mapPreviewTool({...unit_amount:999}) -> resolve would ground
    productName: "medias",
    candidateCount: 1,
    withinCaps: true,
    groundingCorpus: corpus,
  });
  check("invented price (999 absent from operator corpus) -> auto:false",
    invented.auto === false && invented.reasons.some((r) => r.startsWith("ungrounded-numerals")),
    JSON.stringify(invented));

  // --- the grounded, deterministic, reversible write auto-posts (the obvious owner-grounded case)
  const grounded = computeVerdict({
    operationType: "REGISTER_SALE",
    utterance: corpus,
    groundedAmounts: [2, 300],
    productName: "medias",
    candidateCount: 1,
    withinCaps: true,
    groundingCorpus: corpus,
  });
  check("grounded obvious reversible write -> auto:true", grounded.auto === true, JSON.stringify(grounded));

  // --- a numeral grounded by an EARLIER operator turn still auto-posts (multi-turn grounding is
  // the whole flow record, not the single turn): corpus spans "vendi 2 medias" then "a 300".
  const multi = computeVerdict({
    operationType: "REGISTER_SALE",
    utterance: "300", // the current turn is just the price; the quantity grounds to the earlier turn
    groundedAmounts: [2, 300],
    productName: "medias",
    candidateCount: 1,
    withinCaps: true,
    groundingCorpus: "vendi 2 medias\n300",
  });
  check("numeral grounded by an earlier turn in the flow corpus -> auto:true", multi.auto === true, JSON.stringify(multi));

  // --- 3. THE KEYSTONE, in the wiring. The preview route must build grounding from operator_turns
  // (flow-turns), never from the request body. Assert against the route source so a future edit
  // that grounded against the body (the kill risk) fails this test loudly.
  const routeSrc = readFileSync(join(here, "..", "app", "api", "internal", "ops", "preview", "[tool]", "route.ts"), "utf8");
  check("route grounds from operatorTurnsFor (operator_turns), not the body",
    /operatorTurnsFor\(owner, flowNonce\)/.test(routeSrc) && /@\/lib\/flow-turns/.test(routeSrc),
    "route must call operatorTurnsFor(owner, flowNonce)");
  // The utterance + groundingCorpus handed to stageOperation come from `turns`, never from `body`.
  check("utterance + groundingCorpus derive from turns, never body",
    /const groundingCorpus = turns\.map/.test(routeSrc) &&
      /const utterance = turns\.length/.test(routeSrc) &&
      !/utterance:\s*body/.test(routeSrc) &&
      !/groundingCorpus:\s*body/.test(routeSrc),
    "grounding source must be the server record, not the tool args");

  console.log(fails === 0 ? "\nALL PASS" : `\n${fails} FAIL`);
  process.exit(fails ? 1 : 0);
}

main();
