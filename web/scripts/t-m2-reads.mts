// Live read round-trip for spec 010 M2 (T-007..T-011, AC2, AC6, Section D). Exercises each
// internal read endpoint handler directly against the real Beans Neon DB (read-only — this
// family never writes). It proves, against live data:
//   - each endpoint returns { ok:true, <resultKey> } with the exact key the MCP tool lifts
//     (revenue / profit / sales_summary / module / attention);
//   - a request WITHOUT the service token returns the named-error envelope
//     { ok:false, error:{ code, message } } (the forced-error half of the Section D audit);
//   - read_module rejects an unknown module id with invalid_module (400);
//   - business_status.attention is byte-equal to the Hoy route's attention block (T-010).
//
// Requires DATABASE_URL in the env (from .env.local). The service token is set here so the
// guard passes with a request that presents the same value; absent it, the guard 503s and the
// happy path cannot run. Run:
//   npx tsx --env-file=.env.local scripts/t-m2-reads.mts
import process from "node:process";
import { readFileSync } from "node:fs";
import { neonConfig } from "@neondatabase/serverless";

// Route a standalone-script read over Neon's HTTP query path instead of the WebSocket pool the
// app uses on Vercel's Node runtime. Reads are single statements, so fetch is both sufficient
// and more reliable outside a long-lived server. Set before the first query runs.
neonConfig.poolQueryViaFetch = true;

// Set the internal service token before importing anything that reads it, and present the same
// value in every authenticated request below. (The real token is set in Vercel for prod; this
// is the local round-trip's own secret, never a credential.)
process.env.INTERNAL_SERVICE_TOKEN ||= "m2-live-read-token";
const TOKEN = process.env.INTERNAL_SERVICE_TOKEN;
const TENANT = "+5490000000000";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

function authed(body?: unknown): Request {
  return new Request("http://internal/", {
    method: "POST",
    headers: { "x-internal-token": TOKEN!, "x-beans-tenant": TENANT, "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
function unauthed(body?: unknown): Request {
  return new Request("http://internal/", {
    method: "POST",
    headers: { "x-beans-tenant": TENANT, "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function main() {
  if (!process.env.DATABASE_URL) {
    console.log("FAIL  DATABASE_URL is not set — cannot run the live read walk");
    process.exit(1);
  }

  const { POST: readRevenue } = await import("@/app/api/internal/ops/read_revenue/route");
  const { POST: readProfit } = await import("@/app/api/internal/ops/read_profit/route");
  const { POST: readSales } = await import("@/app/api/internal/ops/read_sales_summary/route");
  const { POST: readModule } = await import("@/app/api/internal/ops/read_module/route");
  const { POST: businessStatus } = await import("@/app/api/internal/ops/business_status/route");
  const { attentionSnapshot } = await import("@/lib/domains/command-center");

  // --- revenue
  const rev = await (await readRevenue(authed())).json();
  check("read_revenue ok + revenue key", rev.ok === true && typeof rev.revenue === "object" && typeof rev.revenue.revenue_cents === "number", JSON.stringify(rev));

  // --- profit
  const prof = await (await readProfit(authed())).json();
  check("read_profit ok + profit key", prof.ok === true && typeof prof.profit === "object" && "profit_usd" in prof.profit, JSON.stringify(prof));

  // --- sales summary (clamped limit)
  const salesRes = await readSales(authed({ limit: 5 }));
  const sales = await salesRes.json();
  check("read_sales_summary ok + array", sales.ok === true && Array.isArray(sales.sales_summary), JSON.stringify(sales).slice(0, 180));
  check("read_sales_summary respects limit<=5", sales.ok === true && sales.sales_summary.length <= 5, `len=${sales.sales_summary?.length}`);

  // --- each of the eight modules
  for (const id of ["caja", "productos", "stock", "ventas", "costos", "produccion", "logistica", "proveedores"]) {
    const m = await (await readModule(authed({ module: id }))).json();
    check(`read_module ${id} ok + headline`, m.ok === true && m.module?.module === id && typeof m.module?.headline === "object" && Array.isArray(m.module?.attention), JSON.stringify(m).slice(0, 160));
  }

  // --- invalid module id is a named error, not a silent wrong read
  const bad = await readModule(authed({ module: "no-such-module" }));
  const badBody = await bad.json();
  check("read_module invalid id -> invalid_module 400", bad.status === 400 && badBody.ok === false && badBody.error?.code === "invalid_module", JSON.stringify(badBody));

  // --- business_status
  const bs = await (await businessStatus(authed())).json();
  check("business_status ok + attention key", bs.ok === true && bs.attention && Array.isArray(bs.attention.overdue_arrivals), JSON.stringify(bs).slice(0, 160));

  // --- T-010: business_status.attention is byte-equal to the shared attentionSnapshot() source
  // (the same function GET /api/hoy renders), so the model's "what needs attention" list is the
  // same list the command-center home shows. The hoy GET handler itself is not callable bare in
  // a script (next-auth's guard() reads request-scoped headers), so byte-equality is proven two
  // ways: (1) the endpoint's attention deep-equals the shared source, and (2) a static check
  // that the hoy route sources its attention from attentionSnapshot(), not a private copy.
  const sharedAttn = JSON.stringify(await attentionSnapshot());
  const bsAttn = JSON.stringify(bs.attention);
  check("T-010 business_status attention byte-equal to attentionSnapshot()", bsAttn === sharedAttn, `bs=${bsAttn.slice(0, 80)} shared=${sharedAttn.slice(0, 80)}`);

  // Bind the regression guard to CODE, not prose: strip comments first, then require both the
  // import of attentionSnapshot and a real call to it, so a gutted code path with the comment
  // left behind fails this check (Edut/Bob, council M2).
  const hoyRaw = readFileSync(new URL("../app/api/hoy/route.ts", import.meta.url), "utf8");
  const hoyCode = hoyRaw.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  const hoyImports = /import\s*\{[^}]*\battentionSnapshot\b[^}]*\}\s*from\s*["']@\/lib\/domains\/command-center["']/.test(hoyCode);
  const hoyCalls = /\battentionSnapshot\s*\(/.test(hoyCode);
  check("T-010 /api/hoy sources attention from attentionSnapshot() in code (comments stripped)", hoyImports && hoyCalls, `imports=${hoyImports} calls=${hoyCalls}`);

  // --- Section D forced-error: no token -> named-error envelope 401
  const noTok = await readRevenue(unauthed());
  const noTokBody = await noTok.json();
  check("no service token -> named-error envelope 401", noTok.status === 401 && noTokBody.ok === false && typeof noTokBody.error?.code === "string" && typeof noTokBody.error?.message === "string", JSON.stringify(noTokBody));

  console.log(fails === 0 ? "\nALL PASS" : `\n${fails} FAIL`);
  process.exit(fails ? 1 : 0);
}

main().catch((e) => {
  console.error("live read walk threw:", e);
  process.exit(1);
});
