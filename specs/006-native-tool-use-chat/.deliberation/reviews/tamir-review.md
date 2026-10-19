# Tamir, Rooted Shield, review of spec 006 (native tool-use on the warm box)

I do not veto Dario's choice. I make the tools-enabled box defensible. Spec 005's box was safe on two legs: zero tools, and no `--dangerously-skip-permissions` so a headless turn with no TTY auto-denied any tool call. Native tool-use kicks out both legs. My work is to replace them with positive, testable controls.

## 1. What problem is this actually solving

Collapsing the Gemini multi-agent graph into one direct tool loop so the operator has a single conversational write path over real operations. From my seat the honest framing: it re-opens the injection-to-write surface 005 closed, so the convenience has to be worth a box where untrusted text can drive a confirmed operation.

## 2. Smallest first version that proves the idea

Read-only MCP tools only: the 8 snapshots plus stock and revenue reads. The operation-API bearer is read-scoped, cannot write. This proves the tool loop, the allowlist, and the boot self-check hold with zero write risk. Add exactly one write (REGISTER_SALE) behind the confirm card as the second step, never in the first.

## 3. Three risks that would kill this

1. A blanket `--dangerously-skip-permissions`, or an allowlist a built-in slips past, is remote code execution. Never pass skip-permissions. Posture: `--allowedTools "mcp__beans__*"` as the only positive grant, the existing `--disallowedTools` list kept in full, `--mcp-config` pointing only at the beans server, `--strict-mcp-config` so no inherited server loads, and settings inheritance off. No TTY plus no skip-permissions means anything not in the allowlist still auto-denies.
2. Any DB credential or write/admin-scoped bearer on the box turns an injection into exfiltration. Keep the box holding only three secrets: model token, gateway bearer, and a single-business scoped operation-API bearer. Keep the entrypoint env grep, add the operation-API host to it so no wildcard shape sneaks in.
3. A model-authoritative confirm turns injection into a silent write. The confirm must be server-authoritative (see 4).

## 4. Success at 90 days

Audit shows zero built-in tool executions. Every committed write has a matching app-minted, single-use, args-bound, short-TTL confirm token the model could not forge. The model only proposes; the Beans app renders the card from the proposed args and commits only on an operator click it re-validates. Bearer is rotated and scoped to one tenant, reads plus propose only. Rate limits hold: per-session and global caps on tool calls, tighter on CANCEL_* and DEACTIVATE. Egress from the box is firewalled to the operation-API host and Anthropic only. Every tool call is logged (name, args, caller, confirm-token, commit or deny).

## 5. Atomic tasks

1. Beans MCP server exposing only the named operations; reads first, writes later.
2. Scoped operation-API bearer, single-business, read plus propose, no admin or schema.
3. CLI posture wiring: allowedTools, strict-mcp-config, disallowedTools kept, no skip-permissions.
4. Boot-time tool-posture self-check, fail closed (see 6).
5. Extend entrypoint secret grep for the operation-API host.
6. Server-authoritative confirm token: minted by app, args-bound, single-use, TTL.
7. Per-session and global rate limits plus tighter CANCEL/DEACTIVATE caps.
8. Egress firewall to operation-API host and Anthropic only.
9. Audit log of every tool call with confirm linkage.
10. Injection-corpus test: tenant text that attempts a built-in and an unconfirmed write, both must fail.

## 6. The one thing only my faculty noticed

The entrypoint has a self-check for secrets but none for tool posture. Mirror it: at boot, assert the running `claude` has only `mcp__beans__*` allowed and exit 1 otherwise. The secret grep guards leakage; nothing today guards tool execution, which is the leg native tool-use removes. Make it symmetric and fail closed.
