// The app<->parser contract. The parser (remote on Nomad, or the local fallback)
// turns operator text into a PROPOSAL; it never executes anything. The app
// re-derives the verdict and is the only thing that commits.
export interface Proposal {
  operationType: string;
  args: Record<string, unknown>;
  utterance: string;
  source: "remote" | "fallback";
  note?: string;
}
