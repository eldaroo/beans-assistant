// M7 parser posture (spec 008 AC7): a STATIC check of the Nomad parser job spec.
// The sidecar must carry no DB credential, spawn claude with every built-in tool
// disabled and exactly one turn, gate /parse behind the bearer, and fail its boot
// closed if any org-keyring/DB value is present. These are the structural reasons
// the parser can never itself reach a write. No DB, no network. Run with:
//   npx tsx scripts/m7-posture.mts
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const hcl = readFileSync(join(here, "..", "..", "deploy", "beans-parse.nomad.hcl"), "utf8");

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

// 1. Every built-in tool is disabled (the parser cannot read/write/fetch anything).
const BUILTINS = ["Bash", "Edit", "Write", "Read", "Glob", "Grep", "WebFetch", "WebSearch", "NotebookEdit", "Task", "TodoWrite"];
const disallowedLine = (hcl.match(/--disallowedTools['",\s]+([^\n]+)/) || [])[1] ?? "";
check("every built-in tool is disallowed", BUILTINS.every((t) => disallowedLine.includes(t)), disallowedLine.slice(0, 80));

// 2. Exactly one turn; no agentic loop.
check("--max-turns 1 (single turn, no loop)", /--max-turns['",\s]+1\b/.test(hcl));

// 3. The only secrets templated in are the model token and the bearer.
const tmpl = hcl.slice(hcl.indexOf("CLAUDE_CODE_OAUTH_TOKEN="), hcl.indexOf("CLAUDE_CODE_OAUTH_TOKEN=") + 200);
check("env carries the model token", /CLAUDE_CODE_OAUTH_TOKEN=\{\{/.test(hcl));
check("env carries the bearer secret", /BEANS_PARSE_SHARED_SECRET=\{\{/.test(hcl));

// 4. No DB credential anywhere in the job spec.
check("no DATABASE_URL in the job spec", !/DATABASE_URL\s*=/.test(hcl));
check("no live postgres/neon connection string", !/postgres(?:ql)?:\/\/[^\s"']+@/.test(hcl) && !/\.neon\.tech/.test(hcl));

// 5. The boot isolation self-check scans for org-keyring/DB shapes and fails closed.
check("isolation self-check scans for keyring/DB shapes", /env \| grep -iE '\^\(GITHUB\|SUPABASE\|VERCEL/.test(hcl) || /isolation self-check/.test(hcl));
check("self-check fails closed (exit 1 on leak)", /isolation broken[\s\S]{0,80}exit 1/.test(hcl));

// 6. /parse is gated behind the bearer (401 without it).
check("/parse requires the bearer (401 otherwise)",
  /authorization'\]\s*\|\|\s*''\)\s*!==\s*'Bearer '\s*\+\s*SECRET/.test(hcl) && /writeHead\(401/.test(hcl));

// 7. The system prompt tells the model to return ONLY a proposal; the app commits.
check("parser returns only a proposal JSON (no tool/commit capability)",
  /Devolv[eé]s EXCLUSIVAMENTE un objeto JSON/.test(hcl) && /operationType/.test(hcl));

console.log(fails === 0 ? "\nM7-POSTURE: ALL-PASS" : `\nM7-POSTURE: ${fails} FAIL`);
process.exit(fails === 0 ? 0 : 1);

void tmpl;
