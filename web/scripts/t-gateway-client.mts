// Named test for spec 010 M1 T-001: the native tool-use gateway client. PURE: no network, no
// spawned child — an injected fetch stands in for the beans-ai /run-agent box. Run:
//   npx tsx scripts/t-gateway-client.mts
//
// Proves the /run-agent contract ({prompt, system, turn_nonce} + bearer), the result shape, and
// that every failure mode becomes a typed GatewayError the brain seam can read to decide the
// parser fallback (AC1/AC15) rather than crashing the route.
import { runAgent, gatewayConfigured, agentTimeoutMs, GatewayError } from "@/lib/gateway/client";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

type ResLike = { ok: boolean; status: number; json: () => Promise<unknown> };
function res(status: number, body: unknown): ResLike {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}
const noFire = () => new AbortController().signal; // a signal that never aborts (no dangling timer)

function configured() {
  process.env.BEANS_AGENT_URL = "https://box.example/";
  process.env.BEANS_AGENT_BEARER = "sekret";
}
function unconfigured() {
  delete process.env.BEANS_AGENT_URL;
  delete process.env.BEANS_AGENT_BEARER;
}

async function main() {
  // --- gatewayConfigured reflects both envs
  unconfigured();
  check("gatewayConfigured false when unset", gatewayConfigured() === false);
  configured();
  check("gatewayConfigured true when both set", gatewayConfigured() === true);

  // --- agentTimeoutMs default + override
  delete process.env.BEANS_AGENT_TIMEOUT_MS;
  check("agentTimeoutMs default is 45000", agentTimeoutMs() === 45000, String(agentTimeoutMs()));
  process.env.BEANS_AGENT_TIMEOUT_MS = "12000";
  check("agentTimeoutMs honors the env", agentTimeoutMs() === 12000, String(agentTimeoutMs()));
  delete process.env.BEANS_AGENT_TIMEOUT_MS;

  // --- unconfigured runAgent throws a typed error, never reaches fetch
  unconfigured();
  let threw = "";
  try {
    await runAgent({ utterance: "x", turnNonce: "t1", fetchImpl: () => { throw new Error("should-not-fetch"); } });
  } catch (e) {
    threw = e instanceof GatewayError ? e.code : "wrong-type";
  }
  check("unconfigured runAgent throws gateway_unconfigured", threw === "gateway_unconfigured", threw);

  // --- happy path: contract + result
  configured();
  let seen: { url?: string; headers?: Record<string, string>; body?: unknown } = {};
  const happyFetch = (async (url: string, opts: { headers: Record<string, string>; body: string }) => {
    seen = { url, headers: opts.headers, body: JSON.parse(opts.body) };
    return res(200, { ok: true, text: "  Te quedan 48 medias.  ", path: "read_stock" });
  }) as unknown as typeof fetch;
  const r = await runAgent({ utterance: "cuanto stock de medias", turnNonce: "turn-9", system: "SYS", signal: noFire(), fetchImpl: happyFetch });
  check("happy returns trimmed text", r.text === "Te quedan 48 medias.", JSON.stringify(r.text));
  check("happy returns path", r.path === "read_stock");
  check("endpoint is base + /run-agent (one slash)", seen.url === "https://box.example/run-agent", String(seen.url));
  check("bearer header sent", seen.headers?.["authorization"] === "Bearer sekret", String(seen.headers?.["authorization"]));
  const body = seen.body as { prompt: string; system: string; turn_nonce: string };
  check("body carries the utterance as prompt", body.prompt === "cuanto stock de medias");
  check("body carries the system prompt", body.system === "SYS");
  check("body carries the server turn nonce", body.turn_nonce === "turn-9");

  // --- empty result is not a success
  threw = "";
  const emptyFetch = (async () => res(200, { ok: true, text: "   " })) as unknown as typeof fetch;
  try { await runAgent({ utterance: "x", turnNonce: "t", signal: noFire(), fetchImpl: emptyFetch }); }
  catch (e) { threw = e instanceof GatewayError ? e.code : "wrong"; }
  check("empty text throws gateway_empty", threw === "gateway_empty", threw);

  // --- gateway error envelope surfaces its code
  threw = "";
  const errFetch = (async () => res(502, { ok: false, error: { code: "model-error", message: "boom" } })) as unknown as typeof fetch;
  try { await runAgent({ utterance: "x", turnNonce: "t", signal: noFire(), fetchImpl: errFetch }); }
  catch (e) { threw = e instanceof GatewayError ? e.code : "wrong"; }
  check("502 error envelope throws its code", threw === "model-error", threw);

  // --- non-JSON / unexpected body falls to http_<status>
  threw = "";
  const badJson = (async () => ({ ok: false, status: 500, json: async () => { throw new Error("not json"); } })) as unknown as typeof fetch;
  try { await runAgent({ utterance: "x", turnNonce: "t", signal: noFire(), fetchImpl: badJson }); }
  catch (e) { threw = e instanceof GatewayError ? e.code : "wrong"; }
  check("non-json error throws http_500", threw === "http_500", threw);

  // --- timeout maps to gateway_timeout
  threw = "";
  const timeoutFetch = (async () => { const e = new Error("t"); e.name = "TimeoutError"; throw e; }) as unknown as typeof fetch;
  try { await runAgent({ utterance: "x", turnNonce: "t", signal: noFire(), fetchImpl: timeoutFetch }); }
  catch (e) { threw = e instanceof GatewayError ? e.code : "wrong"; }
  check("TimeoutError maps to gateway_timeout", threw === "gateway_timeout", threw);

  // --- a connection failure maps to gateway_unreachable
  threw = "";
  const downFetch = (async () => { throw new Error("ECONNREFUSED"); }) as unknown as typeof fetch;
  try { await runAgent({ utterance: "x", turnNonce: "t", signal: noFire(), fetchImpl: downFetch }); }
  catch (e) { threw = e instanceof GatewayError ? e.code : "wrong"; }
  check("connection failure maps to gateway_unreachable", threw === "gateway_unreachable", threw);

  unconfigured();
  console.log(fails === 0 ? "\nALL PASS" : `\n${fails} FAIL`);
  process.exit(fails ? 1 : 0);
}

main();
