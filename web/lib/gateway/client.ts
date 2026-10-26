// The native tool-use gateway client (spec 010 M1, T-001, D-058). POSTs the operator turn to
// the beans-ai gateway's /run-agent and returns the assistant's prose. This is the brain that
// replaces the propose-only parser: the gateway runs a native tool-use loop on the Nomad box
// (one disposed claude child, --allowedTools mcp__beans__*) that reads live data through the
// MCP read tools and, from M3, stages write previews through the Next internal-ops API.
//
// This client holds NO model credentials and NO DB credentials: it speaks only to the gateway
// over HTTPS + a shared bearer. The op_token never crosses this wire, and nothing the gateway
// returns here is ever used for grounding (grounding reads operator_turns server-side, D-061).
// When the gateway is unconfigured or unreachable the caller falls back to the deterministic
// parser (D-063), so an unset BEANS_AGENT_URL is a SUPPORTED state (the prod default until M6
// deploys the box), not an error — M1 ships dark.

export class GatewayError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = "GatewayError";
    this.code = code;
  }
}

export type GatewayResult = { text: string; path?: string };

// Both envs present => the gateway is the primary brain for this request. Absent => the route
// stays on the parser fallback with zero behavior change (M1 is inert in prod until M6).
export function gatewayConfigured(): boolean {
  return Boolean(process.env.BEANS_AGENT_URL && process.env.BEANS_AGENT_BEARER);
}

// The synchronous agent budget (T-006, D-063): the per-call timeout must sit UNDER the route
// maxDuration so the route always runs its own parser fallback rather than being killed by the
// platform. Overridable by env for live calibration in M3 (A-Q21). Default 45s; hard-capped at
// 55s so an M3 calibration knob can never be set at/above the 60s route maxDuration, which would
// let the platform kill the route before the fallback fires (a 504 instead of a graceful degrade).
const AGENT_TIMEOUT_CAP_MS = 55000;
export function agentTimeoutMs(): number {
  const n = Number(process.env.BEANS_AGENT_TIMEOUT_MS);
  const chosen = Number.isFinite(n) && n > 0 ? n : 45000;
  return Math.min(chosen, AGENT_TIMEOUT_CAP_MS);
}

type RunAgentArgs = {
  utterance: string;
  turnNonce: string;
  system?: string;
  // The route owns the budget: it passes one AbortSignal.timeout(agentTimeoutMs()). When a
  // caller omits it (a test), the client builds its own from agentTimeoutMs().
  signal?: AbortSignal;
  fetchImpl?: typeof fetch;
};

export async function runAgent({ utterance, turnNonce, system, signal, fetchImpl = fetch }: RunAgentArgs): Promise<GatewayResult> {
  const url = process.env.BEANS_AGENT_URL;
  const bearer = process.env.BEANS_AGENT_BEARER;
  if (!url || !bearer) throw new GatewayError("gateway_unconfigured", "BEANS_AGENT_URL / BEANS_AGENT_BEARER are not set");

  const endpoint = url.replace(/\/$/, "") + "/run-agent";
  const budget = signal ?? AbortSignal.timeout(agentTimeoutMs());

  let res: Response;
  try {
    res = await fetchImpl(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${bearer}` },
      // The gateway's /run-agent contract: { prompt, system, turn_nonce }. The flow nonce and
      // the tenant are threaded into the gateway's MCP env out of band in M3 (T-015), never
      // here and never into the model's view.
      body: JSON.stringify({ prompt: utterance, system: system ?? "", turn_nonce: turnNonce }),
      signal: budget,
    });
  } catch (e) {
    const err = e as Error;
    if (err.name === "TimeoutError" || err.name === "AbortError") {
      throw new GatewayError("gateway_timeout", `gateway timed out after ${agentTimeoutMs()}ms`);
    }
    throw new GatewayError("gateway_unreachable", err.message);
  }

  type RunAgentPayload = { ok?: boolean; text?: string; path?: string; error?: { code?: string; message?: string } };
  let payload: RunAgentPayload | null = null;
  try {
    payload = (await res.json()) as RunAgentPayload;
  } catch {
    payload = null;
  }

  if (!res.ok || !payload || payload.ok !== true || typeof payload.text !== "string") {
    const code = payload?.error?.code ?? `http_${res.status}`;
    const message = payload?.error?.message ?? `gateway returned HTTP ${res.status}`;
    throw new GatewayError(code, message);
  }
  const text = payload.text.trim();
  if (!text) throw new GatewayError("gateway_empty", "gateway returned an empty result");
  return { text, path: payload.path };
}
