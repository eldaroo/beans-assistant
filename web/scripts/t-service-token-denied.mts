// Named test for spec 010 M3 T-013 (AC4): the service token is read-plus-propose only. The
// internal-ops family stages but can NEVER commit; the commit path (/api/ops/confirm) and the
// Undo path (/api/ops/undo) stay session-only and reject the service token forever. PURE: a
// source-level invariant check, no DB and no NextAuth boot. Run: npx tsx scripts/t-service-token-denied.mts
//
// Why source-level and not a live POST: the denial is structural, not a runtime branch. confirm
// and undo authenticate ONLY with auth() (a user session); they never consult internalGuard or the
// x-internal-token header, so a request carrying only the service token has no session and is
// refused with 401 before any commit. Asserting that the commit/undo modules are gated by the
// session substrate and never reference the service-token substrate proves the token can never
// authorize a commit — and that a future edit wiring internalGuard into a commit route (the blast
// radius Tamir bounded in D-060) fails this test loudly.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..", "app");
const read = (...p: string[]) => readFileSync(join(app, ...p), "utf8");

function main() {
  const confirm = read("api", "ops", "confirm", "route.ts");
  const undo = read("api", "ops", "undo", "route.ts");
  const preview = read("api", "internal", "ops", "preview", "[tool]", "route.ts");
  const readStock = read("api", "internal", "ops", "read_stock", "route.ts");

  // --- confirm / undo are session-gated and never touch the service-token substrate
  for (const [name, src] of [["confirm", confirm], ["undo", undo]] as const) {
    check(`/api/ops/${name} authenticates with auth() (session)`, /await auth\(\)/.test(src) && /if \(!session\?\.user\)/.test(src), name);
    check(`/api/ops/${name} never imports internalGuard`, !/internalGuard/.test(src) && !/internal-auth/.test(src), name);
    check(`/api/ops/${name} never reads x-internal-token`, !/x-internal-token/.test(src), name);
  }

  // --- the internal family is the mirror image: service-token gated, never session-gated
  for (const [name, src] of [["preview", preview], ["read_stock", readStock]] as const) {
    check(`internal /${name} authenticates with internalGuard (service token)`, /internalGuard\(/.test(src), name);
    check(`internal /${name} never calls auth() (no session substrate)`, !/await auth\(\)/.test(src), name);
  }

  console.log(fails === 0 ? "\nALL PASS" : `\n${fails} FAIL`);
  process.exit(fails ? 1 : 0);
}

main();
