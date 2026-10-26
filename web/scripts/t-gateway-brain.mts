// Named test for spec 010 M1 T-004a/T-004b: the brain seam (AC1/AC15). PURE: injected fetch.
// Run: npx tsx scripts/t-gateway-brain.mts
//
// The load-bearing claim: the gateway is the PRIMARY brain and the parser is reached ONLY on a
// gateway non-answer. gatewayAnswer returns { answered:true } exactly when the box produced
// prose, and { answered:false, reason } on unconfigured / error / timeout / empty. The route
// takes the parser path iff answered is false, so these cases enumerate the full fallback set.
import { gatewayAnswer } from "@/lib/gateway/brain";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

type ResLike = { ok: boolean; status: number; json: () => Promise<unknown> };
function res(status: number, body: unknown): ResLike {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}
const noFire = () => new AbortController().signal;

function configured() {
  process.env.BEANS_AGENT_URL = "https://box.example";
  process.env.BEANS_AGENT_BEARER = "sekret";
}

async function main() {
  // --- unconfigured: the seam never calls fetch, answers false, reason unconfigured
  delete process.env.BEANS_AGENT_URL;
  delete process.env.BEANS_AGENT_BEARER;
  const u = await gatewayAnswer({ utterance: "cuanto stock", turnNonce: "t", fetchImpl: (() => { throw new Error("no-fetch"); }) as unknown as typeof fetch });
  check("unconfigured -> fall back to parser", u.answered === false && (!u.answered && u.reason === "unconfigured"), JSON.stringify(u));

  configured();

  // --- gateway answers: the parser is NOT reached
  const okFetch = (async () => res(200, { ok: true, text: "Te quedan 48 medias." })) as unknown as typeof fetch;
  const a = await gatewayAnswer({ utterance: "cuanto stock de medias", turnNonce: "t", signal: noFire(), fetchImpl: okFetch });
  check("gateway success -> answered true with the prose", a.answered === true && a.answered && a.reply === "Te quedan 48 medias.", JSON.stringify(a));

  // --- gateway error: fall back, reason carries the code
  const errFetch = (async () => res(502, { ok: false, error: { code: "model-error", message: "boom" } })) as unknown as typeof fetch;
  const e = await gatewayAnswer({ utterance: "x", turnNonce: "t", signal: noFire(), fetchImpl: errFetch });
  check("gateway error -> fall back to parser", e.answered === false && (!e.answered && e.reason === "model-error"), JSON.stringify(e));

  // --- gateway timeout: fall back
  const toFetch = (async () => { const x = new Error("t"); x.name = "TimeoutError"; throw x; }) as unknown as typeof fetch;
  const t = await gatewayAnswer({ utterance: "x", turnNonce: "t", signal: noFire(), fetchImpl: toFetch });
  check("gateway timeout -> fall back to parser", t.answered === false && (!t.answered && t.reason === "gateway_timeout"), JSON.stringify(t));

  // --- gateway empty: fall back (an empty result is not an answer)
  const emptyFetch = (async () => res(200, { ok: true, text: "" })) as unknown as typeof fetch;
  const em = await gatewayAnswer({ utterance: "x", turnNonce: "t", signal: noFire(), fetchImpl: emptyFetch });
  check("gateway empty -> fall back to parser", em.answered === false && (!em.answered && em.reason === "gateway_empty"), JSON.stringify(em));

  delete process.env.BEANS_AGENT_URL;
  delete process.env.BEANS_AGENT_BEARER;
  console.log(fails === 0 ? "\nALL PASS" : `\n${fails} FAIL`);
  process.exit(fails ? 1 : 0);
}

main();
