// M7 guards: audit completeness + rate-limit caps (spec 008 M7 "rate limits,
// audit completeness"). Live against an ephemeral Neon branch. Proves:
//  - every staged write intent appends an audit row (append-only completeness);
//  - the tighter DESTRUCTIVE cap actually fires for the registry's uppercase op
//    names (the case/name mismatch that silently disabled it is fixed), while a
//    non-destructive op under the same load stays within the generous global cap.
// Run via the branch runner:
//   node scripts/parity/neon-branch.mjs run scripts/m7-guards.mts
import { and, count, eq, gte } from "drizzle-orm";
import { db } from "@/lib/db";
import { auditLog } from "@/db/schema";
import { appendAudit, withinCaps, DESTRUCTIVE_OPS } from "@/lib/audit";
import { createProduct } from "@/lib/domains/products";
import { stageOperation } from "@/lib/ops/stage";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

async function main() {
  // --- Audit completeness: staging a write appends exactly its audit row ------
  const N = `grd${Date.now().toString(36)}`;
  await createProduct({ sku: `${N}SKU`, name: `${N} termo`, unitCostCents: 0, unitPriceCents: 30000 });
  const staged = await stageOperation({
    operationType: "ADD_STOCK",
    args: { productRef: `${N} termo`, quantity: 5 },
    utterance: `llegaron 5 ${N} termo`,
  });
  check("stage returned ok", staged.ok === true, staged.ok ? "" : (staged as { message: string }).message);
  if (staged.ok) {
    const [{ c }] = await db
      .select({ c: count() })
      .from(auditLog)
      .where(and(eq(auditLog.opToken, staged.op_token), eq(auditLog.outcome, "staged")));
    check("staged write appended its audit row (completeness)", c === 1, `rows=${c}`);
  }

  // --- Destructive cap fires for the real (uppercase) op names ----------------
  // The registry set is the single source of truth, uppercase, matching the
  // operationType and the audit `name` column. Seed DESTRUCTIVE_CAP destructive
  // rows inside the 60s window, then the cap must refuse the next destructive op.
  check("DESTRUCTIVE_OPS holds uppercase registry names",
    DESTRUCTIVE_OPS.has("CANCEL_SALE") && DESTRUCTIVE_OPS.has("DEACTIVATE_PRODUCT") && !DESTRUCTIVE_OPS.has("cancel_sale"),
    [...DESTRUCTIVE_OPS].join(","));

  for (let i = 0; i < 8; i++) {
    await appendAudit({ name: "CANCEL_SALE", caller: "test", outcome: "staged" });
  }
  const destructiveBlocked = await withinCaps("CANCEL_SALE");
  check("destructive cap fires after 8 in window (fail-closed path reachable)", destructiveBlocked === false);

  // A non-destructive op under the same 8 rows is still within the generous global
  // cap (60), so the tighter cap is scoped to destructive ops only.
  const nonDestructiveOk = await withinCaps("REGISTER_SALE");
  check("non-destructive op not blocked by the destructive cap", nonDestructiveOk === true);

  // Sanity: the destructive rows did count in the window.
  const since = new Date(Date.now() - 60 * 1000).toISOString();
  const [{ c: win }] = await db.select({ c: count() }).from(auditLog).where(gte(auditLog.createdAt, since));
  check("window audit count reflects the appended rows", win >= 9, `win=${win}`);

  console.log(fails === 0 ? "\nM7-GUARDS: ALL-PASS" : `\nM7-GUARDS: ${fails} FAIL`);
  process.exit(fails === 0 ? 0 : 1);
}

main().catch((e) => { console.error("SMOKE-ERROR", e); process.exit(2); });
