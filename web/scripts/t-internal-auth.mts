// Named test for spec 010 M1 T-002 (D-060): the internal-ops service-token guard. PURE: a fake
// headers bag + an injected env, no network. Run: npx tsx scripts/t-internal-auth.mts
//
// The guard is the only door the model's tools may open, and it is read-plus-propose only. This
// proves: a missing token is refused, a wrong token is refused (constant-time), a correct token
// with no tenant is refused, and a correct token + tenant passes with the tenant surfaced. The
// commit-path denial of the service token is an M3 assertion (the routes land there).
import { internalGuard, allowedTenants } from "@/lib/internal-auth";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

function headers(map: Record<string, string>) {
  return { get: (k: string) => (k in map ? map[k] : null) };
}

function main() {
  const envOk = { INTERNAL_SERVICE_TOKEN: "service-token-abc" } as unknown as NodeJS.ProcessEnv;

  // --- not configured
  const nc = internalGuard(headers({ "x-internal-token": "service-token-abc", "x-beans-tenant": "+549" }), {} as NodeJS.ProcessEnv);
  check("missing INTERNAL_SERVICE_TOKEN -> 503", !nc.ok && nc.code === "internal_not_configured" && nc.status === 503, JSON.stringify(nc));

  // --- no token header
  const noTok = internalGuard(headers({ "x-beans-tenant": "+549" }), envOk);
  check("missing x-internal-token -> 401", !noTok.ok && noTok.code === "unauthorized" && noTok.status === 401, JSON.stringify(noTok));

  // --- wrong token, same length (constant-time path still refuses)
  const wrongSame = internalGuard(headers({ "x-internal-token": "service-token-xyz", "x-beans-tenant": "+549" }), envOk);
  check("wrong token same length -> 401", !wrongSame.ok && wrongSame.code === "unauthorized", JSON.stringify(wrongSame));

  // --- wrong token, different length (length mismatch still refuses, no throw)
  const wrongLen = internalGuard(headers({ "x-internal-token": "short", "x-beans-tenant": "+549" }), envOk);
  check("wrong token different length -> 401 (no crash)", !wrongLen.ok && wrongLen.code === "unauthorized", JSON.stringify(wrongLen));

  // --- correct token, missing tenant
  const noTenant = internalGuard(headers({ "x-internal-token": "service-token-abc" }), envOk);
  check("correct token, no tenant -> 400", !noTenant.ok && noTenant.code === "tenant_required" && noTenant.status === 400, JSON.stringify(noTenant));

  // --- correct token, blank tenant (whitespace trims to empty)
  const blankTenant = internalGuard(headers({ "x-internal-token": "service-token-abc", "x-beans-tenant": "   " }), envOk);
  check("correct token, blank tenant -> 400", !blankTenant.ok && blankTenant.code === "tenant_required", JSON.stringify(blankTenant));

  // --- correct token + tenant passes, tenant surfaced (trimmed)
  const good = internalGuard(headers({ "x-internal-token": "service-token-abc", "x-beans-tenant": " +5491100000001 " }), envOk);
  check("correct token + tenant -> ok with trimmed tenant", good.ok && good.tenant === "+5491100000001", JSON.stringify(good));

  // ---------------------------------------------------------------- M3 (T-012): tenant allowlist
  const envAllow = { INTERNAL_SERVICE_TOKEN: "service-token-abc", BEANS_INTERNAL_TENANTS: " +5491100000001 , +5491100000002 " } as unknown as NodeJS.ProcessEnv;

  // allowedTenants parses comma-separated, trims, drops empties
  check("allowedTenants parses + trims", JSON.stringify(allowedTenants(envAllow)) === JSON.stringify(["+5491100000001", "+5491100000002"]), JSON.stringify(allowedTenants(envAllow)));
  check("allowedTenants unset -> []", allowedTenants({} as NodeJS.ProcessEnv).length === 0);

  // a tenant ON the allowlist passes
  const allowed = internalGuard(headers({ "x-internal-token": "service-token-abc", "x-beans-tenant": "+5491100000001" }), envAllow);
  check("allowlisted tenant -> ok", allowed.ok && allowed.tenant === "+5491100000001", JSON.stringify(allowed));

  // a tenant OFF the allowlist is refused 403 (defense in depth behind the token) — a leaked
  // token driving a DIFFERENT business is stopped here
  const denied = internalGuard(headers({ "x-internal-token": "service-token-abc", "x-beans-tenant": "+5491199999999" }), envAllow);
  check("non-allowlisted tenant -> 403 tenant_not_allowed", !denied.ok && denied.code === "tenant_not_allowed" && denied.status === 403, JSON.stringify(denied));

  // allowlist UNSET -> any non-empty tenant accepted (dark-safe default, still behind the token)
  const openDefault = internalGuard(headers({ "x-internal-token": "service-token-abc", "x-beans-tenant": "+anything" }), envOk);
  check("allowlist unset -> non-empty tenant accepted (open default)", openDefault.ok && openDefault.tenant === "+anything", JSON.stringify(openDefault));

  console.log(fails === 0 ? "\nALL PASS" : `\n${fails} FAIL`);
  process.exit(fails ? 1 : 0);
}

main();
