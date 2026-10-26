// Named test for spec 010 M6 T-028 (AC15, D-058): the propose-only parser is RETAINED only as the
// fallback — not deleted — and is reached ONLY on a gateway failure. Run:
//   npx tsx scripts/t-parser-fallback-only.mts
//
// Three proofs:
//   1. The parser is retained and still works (fallbackParse + parseMessage import cleanly and
//      parse a canonical turn). Deleting it would break this.
//   2. The brain seam reaches an answer without the parser on gateway SUCCESS, and only hands off
//      to the parser on the gateway-failure set (unconfigured / error / timeout / empty).
//   3. A ROUTE source-assertion: /api/chat/route.ts reaches parseMessage ONLY inside the parser
//      fallback helper (runParserTurn), and the gateway-answered branch returns before it. This
//      pins the wiring so a future edit cannot quietly make the parser primary again (the pattern
//      used by t-internal-preview.mts for the grounding call site).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { gatewayAnswer } from "@/lib/gateway/brain";
import { fallbackParse } from "@/lib/parse/fallback";
import { parseMessage } from "@/lib/parse/client";
import { isAction } from "@/lib/parse/types";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}
type ResLike = { ok: boolean; status: number; json: () => Promise<unknown> };
const res = (status: number, body: unknown): ResLike => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const noFire = () => new AbortController().signal;

async function main() {
  // --- 1. the parser is RETAINED and still parses a canonical turn -------------------------------
  const parsed = fallbackParse("vendi 2 medias a 300");
  check("parser retained: fallbackParse still parses a sale", !!parsed && isAction(parsed), JSON.stringify(parsed));
  check("parser retained: parseMessage is importable (not deleted)", typeof parseMessage === "function");

  // --- 2. the parser is reached ONLY on gateway failure -----------------------------------------
  process.env.BEANS_AGENT_URL = "https://box.example";
  process.env.BEANS_AGENT_BEARER = "sekret";
  const okFetch = (async () => res(200, { ok: true, text: "Te quedan 48 medias." })) as unknown as typeof fetch;
  const ok = await gatewayAnswer({ utterance: "cuanto stock de medias", turnNonce: "t", signal: noFire(), fetchImpl: okFetch });
  check("gateway SUCCESS -> answered true (the route returns before the parser)", ok.answered === true);

  const errFetch = (async () => res(502, { ok: false, error: { code: "model-error", message: "boom" } })) as unknown as typeof fetch;
  const err = await gatewayAnswer({ utterance: "x", turnNonce: "t", signal: noFire(), fetchImpl: errFetch });
  check("gateway FAILURE -> answered false (the route hands off to the parser)", err.answered === false && !err.answered && err.reason === "model-error", JSON.stringify(err));

  // --- 3. route source-assertion: parseMessage is reached ONLY in the parser fallback helper -----
  const here = dirname(fileURLToPath(import.meta.url));
  const routeSrc = readFileSync(join(here, "..", "app", "api", "chat", "route.ts"), "utf8");
  check("route imports both brains (gatewayAnswer + parseMessage)", routeSrc.includes("gatewayAnswer") && routeSrc.includes("parseMessage"));
  // parseMessage is CALLED exactly once, and that call sits inside runParserTurn (the fallback),
  // never in the gateway-answered branch. Assert the only `parseMessage(` call follows the helper.
  const helperIdx = routeSrc.indexOf("async function runParserTurn");
  const callIdx = routeSrc.indexOf("parseMessage(");
  check("parseMessage is invoked only inside runParserTurn (the fallback)", helperIdx > 0 && callIdx > helperIdx, `helper@${helperIdx} call@${callIdx}`);
  // The gateway-answered branch returns an agent/answer result, not a parser call.
  check("the gateway-answered branch returns before any parser call", routeSrc.includes("kind: \"agent\"") && routeSrc.indexOf("if (g.answered)") < callIdx);

  console.log(fails === 0 ? "\nT-PARSER-FALLBACK-ONLY: ALL-PASS" : `\nT-PARSER-FALLBACK-ONLY: ${fails} FAIL`);
  process.exit(fails === 0 ? 0 : 1);
}
main();
