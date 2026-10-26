// Service-token guard for the internal-ops API (spec 010, D-060). The beans-ai gateway's MCP
// tools reach these routes with a shared INTERNAL_SERVICE_TOKEN (x-internal-token) and the
// tenant pinned out of band (x-beans-tenant) — NEVER a session, and NEVER a tool arg. The model
// holds no DB credentials; this is the only door its tools may open, and the family is
// read-plus-propose only: the commit path (/api/ops/confirm, /api/ops/undo) stays auth()-only
// and rejects this token forever (asserted by the M3 service-token-denied test).
//
// M1 scaffold: a constant-time token compare + tenant presence. M3 (T-012) adds the
// single-business allowlist validation of the tenant. The constant-time compare is here from
// day one so a token guess cannot be timed. Pure (node:crypto only, no next import) so it unit
// tests under tsx with a fake headers object.
import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export type InternalAuthResult =
  | { ok: true; tenant: string }
  | { ok: false; code: string; message: string; status: number };

// Length-independent constant-time equality. Both sides are HMAC'd to a fixed-size (32-byte)
// digest under a per-call random key, then compared with timingSafeEqual over equal-length
// buffers. Because the digests are always 32 bytes regardless of input length, there is no
// early length-mismatch return and thus no length-timing oracle on INTERNAL_SERVICE_TOKEN
// (Tamir, council M1).
function constantTimeEqual(a: string, b: string): boolean {
  const key = randomBytes(32);
  const da = createHmac("sha256", key).update(a, "utf8").digest();
  const db = createHmac("sha256", key).update(b, "utf8").digest();
  return timingSafeEqual(da, db);
}

type HeaderBag = { get(name: string): string | null };

export function internalGuard(headers: HeaderBag, env: NodeJS.ProcessEnv = process.env): InternalAuthResult {
  const expected = env.INTERNAL_SERVICE_TOKEN;
  // The message is lifted into MODEL-visible tool output by the MCP callRead, so it stays
  // generic and never names the env var; the specific misconfiguration is logged server-side
  // (Tamir, council M2). The machine-readable code is unchanged for the M1 guard test.
  if (!expected) {
    console.error("internalGuard: INTERNAL_SERVICE_TOKEN is not set");
    return { ok: false, code: "internal_not_configured", message: "Servicio no disponible", status: 503 };
  }

  const presented = headers.get("x-internal-token") ?? "";
  if (!presented || !constantTimeEqual(presented, expected)) {
    return { ok: false, code: "unauthorized", message: "Missing or invalid internal token", status: 401 };
  }
  const tenant = (headers.get("x-beans-tenant") ?? "").trim();
  if (!tenant) return { ok: false, code: "tenant_required", message: "x-beans-tenant header is required", status: 400 };

  return { ok: true, tenant };
}
