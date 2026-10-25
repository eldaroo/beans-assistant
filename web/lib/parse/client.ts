// The parser client. Calls the stateless Nomad parser (wal-parse pattern) over
// HTTPS+bearer for a proposal; falls back to the local deterministic parser when the
// remote is unset or unreachable. The parser only PROPOSES; the app validates + commits.
import { actionOf, type Proposal } from "@/lib/parse/types";
import { fallbackParse } from "@/lib/parse/fallback";

export async function parseMessage(message: string): Promise<Proposal | null> {
  const url = process.env.BEANS_PARSE_URL;
  const bearer = process.env.BEANS_PARSE_BEARER;
  if (url && bearer) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${bearer}` },
        body: JSON.stringify({ message }),
        signal: AbortSignal.timeout(8000),
      });
      if (res.ok) {
        const j = (await res.json()) as { operationType?: string; args?: Record<string, unknown>; none?: boolean; note?: string };
        if (j?.none) return null;
        if (j?.operationType) {
          // The remote parser still emits one op per turn; wrap it into the
          // ordered-steps action shape. Compound (two-step) turns are built
          // server-side when a product does not resolve, not by the parser.
          return actionOf({ operationType: j.operationType, args: j.args ?? {} }, message, "remote", j.note);
        }
      }
    } catch {
      // network/timeout/parse error -> fall back to the deterministic parser
    }
  }
  return fallbackParse(message);
}
