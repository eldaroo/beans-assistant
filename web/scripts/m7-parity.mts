// M7 parity suite (spec 008 AC4). Reads the golden captured from the REAL Python
// cores (web/scripts/parity/golden.json, produced by parity/oracle.py) and asserts
// the ported TypeScript produces byte-equal output for the SAME fixtures. Pure
// functions only, no DB. The verdict `auto`/`requiresHumanReview` flags are byte-
// exact; verdict reasons are compared as a reason-code set (the float-repr tail,
// e.g. [400.0] vs [400], is the single documented tolerance). Run from web/:
//   npx tsx scripts/m7-parity.mts
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { parseOne, parseNumbers, numeralIsGrounded } from "@/lib/money";
import { computeVerdict } from "@/lib/verdict";
import {
  monthOfIsoWeek,
  unitsInMonth,
  laborPerUnit,
  recompute,
  usdCentsFrom,
  type CostComponent,
} from "@/lib/domains/costing";
import { isScenario, formatReply, type ScenarioResult } from "@/lib/domains/cost-scenario";

const here = dirname(fileURLToPath(import.meta.url));
const golden = JSON.parse(readFileSync(join(here, "parity", "golden.json"), "utf8"));

let fails = 0;
let total = 0;
function check(name: string, got: unknown, want: unknown) {
  total++;
  const g = JSON.stringify(got);
  const w = JSON.stringify(want);
  const ok = g === w;
  if (!ok) {
    fails++;
    console.log(`FAIL  ${name}\n        got : ${g}\n        want: ${w}`);
  }
}

// ---- money --------------------------------------------------------------
for (const c of golden.money.parse_one) {
  check(`money.parseOne(${JSON.stringify(c.raw)})`, parseOne(c.raw), c.out);
}
for (const c of golden.money.parse_numbers) {
  check(`money.parseNumbers(${JSON.stringify(c.text)})`, [...parseNumbers(c.text)].sort((a, b) => a - b), c.out);
}
for (const c of golden.money.numeral_is_grounded) {
  check(
    `money.numeralIsGrounded(${JSON.stringify(c.value)}, "${c.utterance}")`,
    numeralIsGrounded(c.value, parseNumbers(c.utterance)),
    c.out,
  );
}

// ---- verdict ------------------------------------------------------------
for (const row of golden.verdict) {
  const c = row.case;
  const v = computeVerdict({
    operationType: c.operation_type,
    utterance: c.utterance,
    groundedAmounts: c.grounded_amounts,
    productName: c.product_name ?? null,
    candidateCount: c.candidate_count,
    withinCaps: c.within_caps ?? true,
    irreversible: c.irreversible ?? false,
  });
  const name = `verdict[${c.operation_type} | "${c.utterance}"]`;
  check(`${name}.auto`, v.auto, row.auto);
  check(`${name}.requiresHumanReview`, v.requiresHumanReview, row.requires_human_review);
  const codes = [...new Set(v.reasons.map((r) => r.split(":", 1)[0]))].sort();
  check(`${name}.reasonCodes`, codes, row.reason_codes);
}

// ---- costing (pure) -----------------------------------------------------
for (const c of golden.costing.month_of_iso_week) {
  check(`costing.monthOfIsoWeek(${c.week})`, monthOfIsoWeek(c.week), c.out);
}
const rows = golden.costing.units_rows as Array<{ period_week: string; units: number }>;
for (const c of golden.costing.units_in_month) {
  check(`costing.unitsInMonth(${c.month})`, unitsInMonth(rows, c.month), c.out);
}
for (const c of golden.costing.labor_per_unit) {
  check(`costing.laborPerUnit(${c.batch_payment_cents}, ${c.units_completed})`,
    laborPerUnit(c.batch_payment_cents, c.units_completed), c.out);
}
for (const c of golden.costing.usd_cents_from) {
  check(`costing.usdCentsFrom(${c.original_amount_cents}, ${c.fx_rate})`,
    usdCentsFrom(c.original_amount_cents, c.fx_rate), c.out);
}
for (const c of golden.costing.recompute) {
  const components = c.components as CostComponent[];
  const overrides = c.overrides as Record<string, number | null>;
  const { totalCents, status, pendingLabels } = recompute(components, overrides);
  check(`costing.recompute[${c.name}]`,
    { total_cents: totalCents, status, pending_labels: pendingLabels }, c.out);
}

// ---- scenario (pure) ----------------------------------------------------
for (const c of golden.scenario.is_scenario) {
  check(`scenario.isScenario(${JSON.stringify(c.message)})`, isScenario(c.message), c.out);
}
for (const c of golden.scenario.format_reply) {
  const r = c.result as Omit<ScenarioResult, "productId"> & { productId?: number };
  check(`scenario.formatReply[${r.scenarioCountry}/${r.moved}/${r.baselineStatus}-${r.scenarioStatus}]`,
    formatReply({ productId: 1, ...r } as ScenarioResult), c.out);
}

console.log(fails === 0 ? `\nM7-PARITY: ALL-PASS (${total} checks)` : `\nM7-PARITY: ${fails}/${total} FAIL`);
process.exit(fails === 0 ? 0 : 1);
