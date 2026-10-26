// Named test for spec 010 M2 (T-009): the command-center module registry and its validator.
// PURE — no DB, no network. It proves the TS MODULE_IDS the read_module endpoint validates
// against is in lockstep with the MCP read_module enum (deploy/beans-mcp.mjs MODULE_IDS): a
// drift means the gateway would offer the model a module id the endpoint rejects, or the
// endpoint would reject one the gateway offers — a silent dead-end exactly like the one this
// spec exists to kill. Run: npx tsx scripts/t-command-center.mts
import { MODULE_IDS, isModuleId } from "@/lib/domains/command-center";
import { MODULE_IDS as MCP_MODULE_IDS } from "../../deploy/beans-mcp.mjs";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

// Lockstep: the two registries must be the identical set in the identical order.
check(
  "TS MODULE_IDS lockstep with MCP read_module enum",
  JSON.stringify([...MODULE_IDS]) === JSON.stringify([...MCP_MODULE_IDS]),
  `ts=${JSON.stringify(MODULE_IDS)} mcp=${JSON.stringify(MCP_MODULE_IDS)}`,
);
check("eight modules", MODULE_IDS.length === 8, String(MODULE_IDS.length));

for (const id of MODULE_IDS) check(`isModuleId accepts "${id}"`, isModuleId(id));

const junk: unknown[] = ["", "ventas2", "VENTAS", " stock", "__proto__", null, undefined, 3, {}];
for (const j of junk) check(`isModuleId rejects ${JSON.stringify(j)}`, !isModuleId(j));

console.log(fails === 0 ? "\nALL PASS" : `\n${fails} FAIL`);
process.exit(fails ? 1 : 0);
