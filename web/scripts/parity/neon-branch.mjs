// Ephemeral Neon branch runner for M7 live smokes (spec 008). Creates a short-
// lived branch of beans-prod (a copy-on-write snapshot of prod schema + data at
// branch time), runs a tsx smoke against it with DATABASE_URL set to the branch,
// and deletes the branch in a finally so prod data is never touched and no branch
// leaks. The control-plane key is read from the secrets file, never printed.
//
//   node scripts/parity/neon-branch.mjs run scripts/m7-resolution-parity.mts
//
// Secrets path defaults to the QIE-root .qie/secrets/beans-neon.json; override
// with BEANS_NEON_SECRET.
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const API = "https://console.neon.tech/api/v2";
// The beans-prod project lives in the Everyset Neon org; branch create/delete is
// authorized by that org's control-plane key (neon-casting.json `api_key`), while
// the project id comes from beans-neon.json. Both default to the QIE-root secrets;
// override the dir with QIE_SECRETS or each file with BEANS_NEON_SECRET / BEANS_NEON_KEYFILE.
const SECRETS_DIR =
  process.env.QIE_SECRETS ||
  resolve(process.cwd(), "..", "..", "..", "..", "..", ".qie", "secrets");
const PROJECT_FILE = process.env.BEANS_NEON_SECRET || resolve(SECRETS_DIR, "beans-neon.json");
const KEY_FILE = process.env.BEANS_NEON_KEYFILE || resolve(SECRETS_DIR, "neon-casting.json");

const projectSecret = JSON.parse(readFileSync(PROJECT_FILE, "utf8"));
const keySecret = JSON.parse(readFileSync(KEY_FILE, "utf8"));
const KEY = keySecret.api_key || keySecret.control_plane_key || projectSecret.control_plane_key;
const PROJECT = projectSecret.project_id;
if (!KEY || !PROJECT) {
  console.error("neon-branch: missing key or project_id", { KEY_FILE, PROJECT_FILE });
  process.exit(2);
}

async function api(method, path, body) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: {
      authorization: `Bearer ${KEY}`,
      "content-type": "application/json",
      accept: "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`Neon ${method} ${path} -> ${res.status}: ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : {};
}

async function createBranch(name) {
  const out = await api("POST", `/projects/${PROJECT}/branches`, {
    branch: { name },
    endpoints: [{ type: "read_write" }],
  });
  const branchId = out.branch?.id;
  const uri =
    out.connection_uris?.[0]?.connection_uri ||
    out.connection_uris?.[0]?.connection_parameters?.connection_uri;
  if (!branchId || !uri) throw new Error("Neon create: no branch id / connection uri in response");
  return { branchId, uri };
}

async function deleteBranch(branchId) {
  // Endpoints are removed with the branch.
  await api("DELETE", `/projects/${PROJECT}/branches/${branchId}`);
}

async function waitReady(uri, tries = 20) {
  // The fresh endpoint may need a moment to accept connections; the smoke's own
  // first query is the real readiness check, so just return the uri.
  return uri;
}

async function main() {
  const [cmd, smoke] = process.argv.slice(2);
  if (cmd !== "run" || !smoke) {
    console.error("usage: node neon-branch.mjs run <smoke.mts>");
    process.exit(2);
  }
  const name = `m7-smoke-${Date.now()}`;
  let branchId;
  let code = 1;
  try {
    const b = await createBranch(name);
    branchId = b.branchId;
    const uri = await waitReady(b.uri);
    console.error(`[neon-branch] created ${name} (${branchId}); running ${smoke}`);
    const r = spawnSync("npx", ["tsx", smoke], {
      stdio: "inherit",
      env: { ...process.env, DATABASE_URL: uri, DATABASE_URL_UNPOOLED: uri },
      shell: process.platform === "win32",
    });
    code = r.status ?? 1;
  } finally {
    if (branchId) {
      try {
        await deleteBranch(branchId);
        console.error(`[neon-branch] deleted ${branchId}`);
      } catch (e) {
        console.error(`[neon-branch] WARNING: could not delete ${branchId}: ${e.message}`);
      }
    }
  }
  process.exit(code);
}

main().catch((e) => {
  console.error("[neon-branch] error:", e.message);
  process.exit(3);
});
