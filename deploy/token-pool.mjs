// deploy/token-pool.mjs — in-memory Claude subscription token rotation for the beans-ai gateway.
//
// The gateway authenticates headless with CLAUDE_CODE_OAUTH_TOKEN (a subscription token, not an
// API key). One subscription hits its usage window and the gateway goes silent until it resets.
// This holds several tokens (one per account: a primary plus one or two backups) and rotates to
// the next healthy one the instant a turn comes back "usage limit reached".
//
// SIMPLE variant (Dario's call, 2026-10-19): the token list lives in the Nomad Variable alongside
// the bearer, and benching is in-memory. No database. On a restart the benched state resets, which
// self-corrects: a still-exhausted token just re-benches on its next use (cheap). The richer
// Neon-backed store Quinn uses (quinn-discord/token-pool.mjs + db.mjs) is the promotion path if
// beans ever needs benched state to survive restarts or be shared; the pure detection below is
// lifted from that module unchanged so the two stay in sync.
//
// A subscription token can only be minted by an interactive `claude setup-token` browser login;
// it can never be generated. Dario seeds the list into the Nomad Variable.

const DEFAULT_COOLDOWN_MIN = Number(process.env.BEANS_TOKEN_COOLDOWN_MIN) || 60;

// ── Pure detection (lifted from quinn-discord/token-pool.mjs, kept identical) ──────────────
// Decide if `text` (a claude run's output) is a subscription-limit failure, and pull the reset
// time if present. The machine form is "usage limit reached|<unix-epoch>"; human phrasings carry
// no parseable reset.
export function detectExhaustion(text) {
  if (!text) return { exhausted: false, resetAt: null };
  const t = String(text);
  const epochM = t.match(/usage limit reached\s*[|:]\s*(\d{10,13})/i);
  if (epochM) {
    let n = Number(epochM[1]);
    if (n < 1e12) n *= 1000; // seconds -> ms
    const d = new Date(n);
    return { exhausted: true, resetAt: isNaN(d.getTime()) ? null : d };
  }
  const SIGNATURES = [
    /usage limit reached/i,
    /reached your (?:usage )?limit/i,
    /\b5-hour limit reached\b/i,
    /\bweekly limit reached\b/i,
    /\blimit will reset\b/i,
    /you'?ve (?:hit|reached) your [^.\n]*limit/i,
  ];
  if (SIGNATURES.some((re) => re.test(t))) return { exhausted: true, resetAt: null };
  return { exhausted: false, resetAt: null };
}

export function cooldownReset(now = new Date()) {
  return new Date(now.getTime() + DEFAULT_COOLDOWN_MIN * 60 * 1000);
}

export function allExhaustedMessage(reset) {
  const when = reset ? ` La primera se resetea alrededor de ${new Date(reset).toISOString()}.` : '';
  return `Todas las cuentas de Beans estan en su limite de uso.${when} Agrega una cuenta o espera el reset.`;
}

// Parse the token list from env. Accepts CLAUDE_CODE_OAUTH_TOKENS as a JSON array OR a
// newline/comma-separated list, and the single CLAUDE_CODE_OAUTH_TOKEN for back-compat. Order is
// preserved (primary first), empties dropped, duplicates removed.
export function parseTokens(env = process.env) {
  const out = [];
  const push = (v) => {
    const s = String(v || '').trim();
    if (s && !out.includes(s)) out.push(s);
  };
  const many = (env.CLAUDE_CODE_OAUTH_TOKENS || '').trim();
  if (many) {
    if (many.startsWith('[')) {
      try { JSON.parse(many).forEach(push); } catch { /* fall through to split */ }
    }
    if (!out.length) many.split(/[\n,]/).forEach(push);
  }
  push(env.CLAUDE_CODE_OAUTH_TOKEN);
  // Numbered back-compat: CLAUDE_CODE_OAUTH_TOKEN_2, _3, ...
  for (let i = 2; i <= 9; i++) push(env['CLAUDE_CODE_OAUTH_TOKEN_' + i]);
  return out;
}

function tail(token) {
  return '…' + String(token).slice(-6);
}

// In-memory pool: a list of tokens, each benchable until a reset time.
export class TokenPool {
  constructor(tokens = []) {
    this.entries = tokens.map((token, i) => ({ token, exhaustedUntil: null, label: 'acct-' + (i + 1) }));
  }

  get size() {
    return this.entries.length;
  }

  _healthy(now) {
    const t = now instanceof Date ? now.getTime() : now;
    return this.entries.filter((e) => !e.exhaustedUntil || e.exhaustedUntil.getTime() <= t);
  }

  // The token to spawn with: the first healthy one, or null when the pool is empty/all-benched.
  active(now = new Date()) {
    const h = this._healthy(now);
    return h.length ? h[0].token : null;
  }

  bench(token, resetAt) {
    const e = this.entries.find((x) => x.token === token);
    if (e) e.exhaustedUntil = resetAt instanceof Date ? resetAt : cooldownReset();
  }

  allBenched(now = new Date()) {
    return this.size > 0 && this._healthy(now).length === 0;
  }

  earliestReset() {
    const times = this.entries.map((e) => e.exhaustedUntil).filter(Boolean).map((d) => d.getTime());
    return times.length ? new Date(Math.min(...times)) : null;
  }

  // Masked board for /health; never exposes a token.
  statuses(now = new Date()) {
    const t = now.getTime();
    return this.entries.map((e, i) => ({
      label: e.label,
      tail: tail(e.token),
      active: i === 0 ? undefined : undefined, // active is derived; omit to avoid implying order
      benched: !!(e.exhaustedUntil && e.exhaustedUntil.getTime() > t),
      until: e.exhaustedUntil ? e.exhaustedUntil.toISOString() : null,
    }));
  }
}

// The env a spawned claude child should carry: the active token overrides whatever is ambient, so
// rotation takes effect on the next spawn. Pure so the wiring is unit-testable without a binary.
export function childSpawnEnv(baseEnv, activeToken) {
  if (!activeToken) return baseEnv;
  return { ...baseEnv, CLAUDE_CODE_OAUTH_TOKEN: activeToken };
}
