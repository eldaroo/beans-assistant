// Named test for spec 010 M5 T-027 (AC12, ports spec 007 AC12): the per-session / global
// tool-call caps, tighter on cancels and deactivations. PURE: no DB (the arithmetic is extracted
// into capDecision so it is testable without a live audit table). Run: npx tsx scripts/t-audit-caps.mts
//
// The audit log itself (appendAudit, every write intent via stageOperation + every read tool call
// via auditToolCall) is DB-backed and exercised by the smoke scripts; here we drive the CAP
// decision, which is the load-bearing guard: a hijacked or runaway loop is stopped by the window
// caps, and destructive ops (cancels + deactivations + cancel-last) hit a tighter cap first.
import { capDecision, isDestructive } from "@/lib/audit";
import { DESTRUCTIVE_OP_TYPES } from "@/lib/ops/registry";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

const CAPS = { global: 60, destructive: 8 };

// --- 1. the global cap bounds all write intents -------------------------------------------------
check("under the global cap -> allowed", capDecision(59, 0, false, CAPS) === true);
check("at the global cap -> blocked", capDecision(60, 0, false, CAPS) === false);
check("over the global cap -> blocked (even non-destructive)", capDecision(100, 0, false, CAPS) === false);

// --- 2. the destructive cap is TIGHTER and applies on top of the global cap ---------------------
check("destructive under its tighter cap (but under global) -> allowed", capDecision(20, 7, true, CAPS) === true);
check("destructive AT its tighter cap -> blocked, though far under the global cap", capDecision(20, 8, true, CAPS) === false);
check("a NON-destructive op at the destructive-count is unaffected by the destructive cap", capDecision(20, 8, false, CAPS) === true);

// --- 3. destructive classification is wired to the registry's single source of truth ------------
for (const t of ["CANCEL_SALE", "CANCEL_EXPENSE", "CANCEL_STOCK", "DEACTIVATE_PRODUCT", "CANCEL_LAST"]) {
  check(`${t} is destructive`, isDestructive(t) === true && DESTRUCTIVE_OP_TYPES.has(t));
}
check("REGISTER_SALE is NOT destructive", isDestructive("REGISTER_SALE") === false);
check("isDestructive is case-insensitive", isDestructive("cancel_sale") === true);

// --- 4. drive the tighter cap in a loop: a cancel burst is cut off at the destructive cap -------
let destructiveTotal = 0;
const allowed: boolean[] = [];
for (let i = 0; i < 12; i++) {
  const ok = capDecision(destructiveTotal, destructiveTotal, true, CAPS); // all calls destructive
  allowed.push(ok);
  if (ok) destructiveTotal++;
}
check(`a 12-cancel burst -> exactly ${CAPS.destructive} allowed`, allowed.filter(Boolean).length === CAPS.destructive, JSON.stringify(allowed));

console.log(fails === 0 ? "\nT-AUDIT-CAPS: ALL-PASS" : `\nT-AUDIT-CAPS: ${fails} FAIL`);
process.exit(fails === 0 ? 0 : 1);
