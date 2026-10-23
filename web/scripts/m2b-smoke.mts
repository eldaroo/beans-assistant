// M2b integration smoke: costing chain (pending->complete + margin + indirect
// allocation), production, suppliers, logistics against a live Neon branch.
import { createProduct } from "@/lib/domains/products";
import * as cost from "@/lib/domains/costing";
import * as prod from "@/lib/domains/production";
import * as sup from "@/lib/domains/suppliers";
import * as log from "@/lib/domains/logistics";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

async function main() {
  const C = "Colombia";
  const p = await createProduct({ sku: `TEST-BOM-${Date.now()}`, name: "Pulsera test", unitCostCents: 0, unitPriceCents: 1000 });

  // Materials via BOM: one input priced at 50c/unit, quantity 2 -> 100c.
  const ci = await cost.recordCostInput("Cafe test", "cafe");
  await cost.recordInputPurchase({ costInputId: ci, originalCurrency: "USD", originalAmountCents: 50, fxRate: 1, quantity: 1 });
  await cost.recordBomLine(p.id, ci, C, 2);

  // Partial: only materials filled -> parcial, margin pending.
  const partial = await cost.landedCost(p.id, C);
  check("landed cost is PARCIAL with 5 pending", partial.status === "parcial" && partial.pendingLabels.length === 5, `total=${partial.totalCents}`);
  check("materials summed, not zero", partial.totalCents === 100, `${partial.totalCents}`);
  const mPartial = await cost.margin(p.id, C);
  check("margin pending on partial cost", mPartial.marginCents === null && mPartial.pendingReason!.startsWith("costo parcial"));

  // Fill the rest. indirect = pool / units-produced-in-month.
  await cost.recordLaborBatch(p.id, C, 200, 10); // 20c/unit
  await cost.recordPackagingCost(p.id, C, 30);
  await cost.recordShippingLane(p.id, C, 40, "lane");
  await cost.recordCustomsDuty(p.id, C, 50, "duty");
  await cost.recordIndirectPool(C, "2026-01", 1000);
  await prod.recordProduction({ country: C, periodWeek: "2026-W02", unitsProduced: 100 }); // W02 2026 -> Jan -> 100u

  const complete = await cost.landedCost(p.id, C);
  check("landed cost COMPLETE after all six filled", complete.status === "completo", complete.pendingLabels.join(","));
  check("landed total = 100+20+30+40+50+10 = 250", complete.totalCents === 250, `${complete.totalCents}`);
  const m = await cost.margin(p.id, C);
  check("margin = price 1000 - 250 = 750", m.marginCents === 750, `${m.marginCents}`);

  // Production read.
  const pw = await prod.currentWeek(C);
  check("production currentWeek reports 100 units", pw?.unitsProduced === 100, `${pw?.unitsProduced}`);

  // Suppliers.
  const before = await sup.countActive();
  await sup.createSupplier({ name: "Proveedor test", country: C });
  check("createSupplier raises active count", (await sup.countActive()) === before + 1);

  // Logistics lens on the same shipping/customs rows.
  const lanes = await log.lanesFor(p.id);
  const col = lanes.find((l) => l.country === C)!;
  check("logistics lane complete, total = ship+customs = 90", col.isComplete && col.totalCents === 90, `${col.totalCents}`);

  console.log(fails === 0 ? "\nM2B-SMOKE: ALL-PASS" : `\nM2B-SMOKE: ${fails} FAIL`);
  process.exit(fails === 0 ? 0 : 1);
}

main().catch((e) => { console.error("SMOKE-ERROR", e); process.exit(2); });
