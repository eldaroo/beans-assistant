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

  const mb = mapPreviewTool("register_sale", {});
  check("register_sale without a product -> bad_tool_args", !mb.ok && mb.code === "bad_tool_args", JSON.stringify(mb));

  // --- M4 (T-018): the rest of the reversible set round-trips through the box. ----------------
  // register_expense { amount (whole), description, category? } -> REGISTER_EXPENSE { amountCents, description }
  const me = mapPreviewTool("register_expense", { amount: 500, description: "envio", category: "logistica" });
  check("register_expense maps to REGISTER_EXPENSE { amountCents, description }",
    me.ok && me.input.operationType === "REGISTER_EXPENSE"
      && (me.input.args as Record<string, unknown>).amountCents === 50000
      && (me.input.args as Record<string, unknown>).description === "envio",
    JSON.stringify(me));
  check("register_expense drops the non-op `category` arg (keystone: no stray arg leaks through)",
    me.ok && !("category" in (me.input.args as Record<string, unknown>)), JSON.stringify(me));
  const meBad = mapPreviewTool("register_expense", { amount: 500 });
  check("register_expense without a description -> bad_tool_args", !meBad.ok && meBad.code === "bad_tool_args", JSON.stringify(meBad));
  const meNeg = mapPreviewTool("register_expense", { amount: -10, description: "x" });
  check("register_expense with a negative amount -> bad_tool_args (never a negative-cost expense)", !meNeg.ok && meNeg.code === "bad_tool_args", JSON.stringify(meNeg));

  // add_stock { product, quantity } -> ADD_STOCK { productRef, quantity } (product resolved server-side)
  const mas = mapPreviewTool("add_stock", { product: "termos", quantity: 10 });
  check("add_stock maps to ADD_STOCK { productRef, quantity }",
    mas.ok && mas.input.operationType === "ADD_STOCK"
      && (mas.input.args as Record<string, unknown>).productRef === "termos"
      && (mas.input.args as Record<string, unknown>).quantity === 10,
    JSON.stringify(mas));
  const masStr = mapPreviewTool("add_stock", { product: "termos", quantity: "7" });
  check("add_stock stringified quantity '7' coerces to 7 (not default 1)",
    masStr.ok && (masStr.input.args as Record<string, unknown>).quantity === 7, JSON.stringify(masStr));
  const masBad = mapPreviewTool("add_stock", { quantity: 3 });
  check("add_stock without a product -> bad_tool_args", !masBad.ok && masBad.code === "bad_tool_args", JSON.stringify(masBad));

  // the confirm-only tools are wired as of M5 (T-022); the full mapping coverage lives in
  // t-confirm-tools.mts. Here we only re-affirm that deactivate_product now maps (no longer a
  // no-op) and that a genuinely unknown tool is still a clean unsupported_tool error.
  const mu = mapPreviewTool("deactivate_product", { product: "termo" });
  check("confirm-only tool deactivate_product is wired (M5) -> DEACTIVATE_PRODUCT", mu.ok && "input" in mu && mu.input.operationType === "DEACTIVATE_PRODUCT", JSON.stringify(mu));
  const unknownTool = mapPreviewTool("exfiltrate_db", { url: "x" });
  check("an unknown tool -> unsupported_tool error (never a silent no-op)", !unknownTool.ok && "code" in unknownTool && unknownTool.code === "unsupported_tool", JSON.stringify(unknownTool));

  // --- M4 (T-020): the auto verdict re-proven on the agent path for the whole reversible set. --
  // For each reversible op, the grounded single-turn write auto-posts and a model-invented numeral
  // (present in the args, absent from the operator corpus) fails grounding -> confirm card.
  const expGrounded = computeVerdict({
    operationType: "REGISTER_EXPENSE", utterance: "gaste 500 en envio",
    groundedAmounts: [500], productName: null, candidateCount: 1, withinCaps: true, groundingCorpus: "gaste 500 en envio",
  });
  check("REGISTER_EXPENSE grounded single-turn -> auto:true", expGrounded.auto === true, JSON.stringify(expGrounded));
  const expInvented = computeVerdict({
    operationType: "REGISTER_EXPENSE", utterance: "gaste algo en envio",
    groundedAmounts: [999], productName: null, candidateCount: 1, withinCaps: true, groundingCorpus: "gaste algo en envio",
  });
  check("REGISTER_EXPENSE invented amount (999 absent from corpus) -> auto:false",
    expInvented.auto === false && expInvented.reasons.some((r) => r.startsWith("ungrounded-numerals")), JSON.stringify(expInvented));
  const stockGrounded = computeVerdict({
    operationType: "ADD_STOCK", utterance: "entraron 10 termos",
    groundedAmounts: [10], productName: "termos", candidateCount: 1, withinCaps: true, groundingCorpus: "entraron 10 termos",
  });
  check("ADD_STOCK grounded single-turn -> auto:true", stockGrounded.auto === true, JSON.stringify(stockGrounded));
  const stockInvented = computeVerdict({
    operationType: "ADD_STOCK", utterance: "entraron termos",
    groundedAmounts: [50], productName: "termos", candidateCount: 1, withinCaps: true, groundingCorpus: "entraron termos",
  });
  check("ADD_STOCK invented quantity (50 absent from corpus) -> auto:false",
    stockInvented.auto === false && stockInvented.reasons.some((r) => r.startsWith("ungrounded-numerals")), JSON.stringify(stockInvented));

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

  // --- a sale assembled across turns confirms, never auto-posts (spec 010 M4, D-064 / AC14):
  // corpus spans "vendi 2 medias" then "300". The grounding still succeeds against the corpus
  // (no ungrounded-numerals), but the current turn "300" grounds neither the quantity nor the
  // product, so the consent gate forces auto:false. This supersedes the spec-009 M5 behavior.
  const multi = computeVerdict({
    operationType: "REGISTER_SALE",
    utterance: "300", // the current turn is just the price; the quantity is from the earlier turn
    groundedAmounts: [2, 300],
    productName: "medias",
    candidateCount: 1,
    withinCaps: true,
    groundingCorpus: "vendi 2 medias\n300",
  });
  check("multi-turn-assembled sale confirms (D-064) -> auto:false, consent-gated not ungrounded",
    multi.auto === false && multi.reasons.includes("multi-turn-consent-gate") && !multi.reasons.some((r) => r.startsWith("ungrounded-numerals")),
    JSON.stringify(multi));

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

  // --- 4. THE CONSENT-GATE CALLER INVARIANT, pinned at the call site (council: Winston HIGH / Edut).
  // D-064's consent gate (verdict.ts) infers "assembled across turns" from `corpus !== utterance`.
  // That is sound ONLY while the route passes utterance = the CURRENT (latest) operator turn and
  // groundingCorpus = the full-flow JOIN. If a future edit collapsed the two (e.g. utterance = the
  // join), the gate would silently go inert with no failing unit test, because the computeVerdict
  // tests call it with hand-split args. Pin the distinction against the route source so that
  // regression fails loudly here.
  check("route sets utterance = the LATEST operator turn (not the whole corpus)",
    /const utterance = turns\.length \? turns\[turns\.length - 1\]\.text/.test(routeSrc),
    "utterance must be the current turn (turns[last]) so the consent gate can detect a multi-turn span");
  check("route sets groundingCorpus = the JOIN of all turns (distinct from utterance)",
    /const groundingCorpus = turns\.map\(\(t\) => t\.text\)\.join\("\\n"\)/.test(routeSrc),
    "groundingCorpus must be the full-flow join so corpus !== utterance holds across turns");

  // --- 5. T-020 derivation seam (council: Bob). The verdict re-proofs above feed groundedAmounts by
  // hand ([500], [10]); confirm the hand-fed expense value matches what REGISTER_EXPENSE.resolve
  // actually derives. registry.ts REGISTER_EXPENSE.resolve returns groundedAmounts = [amountCents/100];
  // the map produced amountCents = 50000, so the real derived grounded amount is 500 — the value the
  // T-020 verdict assertion uses. (Kept pure: mirror the formula rather than import the DB-coupled
  // registry; the full map -> stage -> groundedAmounts wiring is covered by the shared M3 route test.)
  check("expense derivation: map amountCents 50000 grounds as [500] (matches REGISTER_EXPENSE.resolve)",
    me.ok && ((me.input.args as Record<string, number>).amountCents / 100) === 500, JSON.stringify(me));

  console.log(fails === 0 ? "\nALL PASS" : `\n${fails} FAIL`);
  process.exit(fails ? 1 : 0);
}

main();
