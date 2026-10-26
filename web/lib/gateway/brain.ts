// The brain seam (spec 010 M1, T-004a/T-004b, D-058). This is the one place that decides
// whether the native tool-use gateway or the deterministic parser answers a turn. It is a pure,
// injected-fetch-testable unit so AC1/AC15 ("the gateway is primary; parseMessage is reached
// ONLY on gateway error or timeout") can be proven without standing up the whole route.
//
// gatewayAnswer returns { answered: true } ONLY when the gateway produced prose. Every other
// outcome — unconfigured, HTTP error, model error, timeout, empty — returns { answered: false }
// with the reason, and the route falls through to the parser. So the parser is unreachable on a
// gateway success and reachable on exactly the gateway-failure set.
import { GatewayError, agentTimeoutMs, gatewayConfigured, runAgent } from "@/lib/gateway/client";
import { TIMONEL_SYSTEM } from "@/lib/gateway/system";

export type BrainOutcome = { answered: true; reply: string } | { answered: false; reason: string };

export async function gatewayAnswer(args: {
  utterance: string;
  turnNonce: string;
  signal?: AbortSignal;
  fetchImpl?: typeof fetch;
}): Promise<BrainOutcome> {
  if (!gatewayConfigured()) return { answered: false, reason: "unconfigured" };
  try {
    const r = await runAgent({
      utterance: args.utterance,
      turnNonce: args.turnNonce,
      system: TIMONEL_SYSTEM,
      signal: args.signal ?? AbortSignal.timeout(agentTimeoutMs()),
      fetchImpl: args.fetchImpl,
    });
    return { answered: true, reply: r.text };
  } catch (e) {
    // The reason is the GatewayError code (gateway_timeout, gateway_unreachable, http_4xx,
    // model-error, gateway_empty, ...) so the fallback decision is observable in a test.
    return { answered: false, reason: e instanceof GatewayError ? e.code : "gateway_error" };
  }
}
