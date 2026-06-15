---
spec: timonel-pending-operations
appends_to: ARCHITECTURE.md
next_ordinal: D-007
author: Winston (BuildOS Architect, architecture-author role)
mode: update
---

# Architecture delta: Timonel deferred-operation completion

> Append-only delta, D-007 through D-012. D-001..D-006 untouched. Quinn merges this into ARCHITECTURE.md.

## System shape

A paused write operation becomes a structured record, not prose in the history buffer. When `write_agent` blocks a sale on a missing field, it emits a `pending_operation` (op type, resolved entities, the named missing field), which `ChatService` persists keyed by phone with a TTL. Next turn a deterministic `resume_gate` node runs before the router: if a record exists and the reply deterministically supplies the missing field, it fills the field, rebuilds the original entities, and routes into the resolver/write arm. The router never sees the resume turn. A cancel or unmatched reply clears the record and falls through to today's cold-classify path. An idempotency token keeps a retried turn from recording a sale twice.

| Name | Responsibility | Owns |
|------|----------------|------|
| write_agent | emit the pending record on a missing-field block | `pending_operation` delta |
| pending (new, `agents/pending.py`) | build, match, complete records (pure) | PendingOperation shape + field-match |
| ChatService | persist/expire the record per phone | per-phone pending store + TTL |
| resume_gate (new) | fill + rebuild + route before the router | resume decision + entity reconstruction |
| router | unchanged; never runs on a resume hit | intent/operation classification |

## Decision log

Panelist source for D-007 through D-012: Winston.

### D-007: The resume path is deterministic code, not a second router call

- **Chosen.** A `resume_gate` node runs before decomposer/router. When a pending record matches the reply, it rebuilds the stored entities in code and routes directly to the resolver.
- **Alternatives.** (a) Enrich the router prompt via `pending_entities` so the LLM re-extracts. (b) Re-ask the router constrained to the pending op.
- **Why this won.** The constraint requires deterministic correctness. The router is Gemini flash, the named unreliable point, and a wrong completion is a wrong financial record. Determinism is available.
- **Why alternatives lost.** (a) is the current bug: the LLM dropped the product across two turns with context present. (b) puts correctness behind a probabilistic call.
- **Implications.** New entry node ahead of decomposer; the router's "Example 3b" is no longer load-bearing.

### D-008: The pending record lives in the per-phone in-process store, not the tenant DB

- **Chosen.** Persist `PendingOperation` alongside the existing `_history_by_key` class state in `ChatService`, keyed by phone, expired by the same TTL.
- **Alternatives.** (a) A row in the per-tenant SQLite/Postgres DB. (b) A new store.
- **Why this won.** A pending operation is conversational working state with the history buffer's lifetime and key, and must not survive a restart: a half-finished sale resumed after a deploy is a hazard.
- **Why alternatives lost.** (a) The tenant DB holds committed facts; an uncommitted intent there invites a reader treating it as real, and restart-survival is the failure we reject. (b) A new store duplicates the buffer's TTL and keying.
- **Implications.** Single-worker assumption inherited and acceptable; when #63 makes history durable, the record rides the same migration.

### D-009: A new `PendingOperation` type, not the existing `pending_entities` seam

- **Chosen.** A `PendingOperation` carrying `operation_type`, the resolved entities to complete (`product_id`, `quantity`), `missing_fields`, `op_token`, `created_at`. `pending_entities` stays a router-prompt hint, untouched.
- **Alternatives.** Extend `pending_entities` to carry resolved ids and drive resume off it.
- **Why this won.** `pending_entities` is a `{name, missing_fields}` prompt hint: no resolved `product_id`, no quantity, no token, and it only populates when `missing_fields` is non-empty (the sale-needs-price branch sets none). Resume needs resolved state.
- **Why alternatives lost.** One shape spanning an LLM-hint role and a determinism-critical role makes each constrain the other.
- **Implications.** `write_agent`'s sale-price block, returning no pending data today, now emits a `PendingOperation` with `product_id` and `quantity` in hand.

### D-010: Completion is idempotent via an op_token recorded at commit

- **Chosen.** Each `PendingOperation` is stamped with an `op_token` at creation. Resume clears the record before commit; the committed sale records the token; a second resume of the same token is refused.
- **Alternatives.** (a) Trust the single-worker model, skip the token. (b) Dedupe by (product, quantity, minute) heuristic.
- **Why this won.** Never double-record a sale is the hard constraint. A retried turn, double-tapped send, or graph retry must commit once; only a token survives all.
- **Why alternatives lost.** (a) In-process storage does not stop a retried turn resuming a still-present record. (b) A heuristic can suppress a legitimately repeated sale.
- **Implications.** Resume clears-then-commits: a crash mid-commit loses the resume, not risks a double.

### D-011: The pending record expires by TTL and is cleared on cancel or change of mind

- **Chosen.** A record older than the history TTL never resumes. A cancel, or any reply the gate cannot match to the missing field, clears it and falls through to the cold path.
- **Alternatives.** Keep the record until explicitly resumed; resume on any numeric reply.
- **Why this won.** Handling cancel and change-of-mind mid-detour is in the constraint. A pause is not a lock; a stale resume is a wrong financial record, so expiry and cancel-clears default safe.
- **Why alternatives lost.** An indefinitely held record resumes a phantom an hour later; resuming on any number guesses, which the constraint forbids.
- **Implications.** The match fills only when the reply unambiguously is the missing field; otherwise it clears and re-asks.

### D-012: Resume serves only fully-resolved paused operations in v1

- **Chosen.** Resume fires only when the paused operation holds every entity except the one missing field. Operations needing fresh disambiguation cold-classify.
- **Alternatives.** A general resume that re-resolves arbitrary missing entities across turns.
- **Why this won.** A resolved-except-one-field pause is a closed, testable transition. Re-resolving an arbitrary entity reintroduces the LLM, which D-007 forbids.

## Conventions

- **Keying + expiry.** Keyed by phone via `_history_key`, one record per phone. Reuse `_context_ttl_seconds` and `_expire_if_stale`; an expired record is dropped.
- **Idempotency.** `op_token` generated at creation, cleared before commit, recorded with the committed operation; a duplicate token is a no-op.
- **One writer per fact.** `write_agent` writes the record on a block; `resume_gate` reads and clears it; the database owns the committed sale. The gate rebuilds from stored ids.
- **Fail-open.** The gate matches nothing it is unsure of; on any internal failure it passes the turn to today's path unchanged.
- **Observability.** One breadcrumb (`[Resume] completing <op> product=<id>`) per resume hit.

## Non-goals

- Not the durability rewrite of #63; the record is in-process and dies on restart.
- Not an LLM-based extractor on the resume path; the match is deterministic (D-007).
- No new operation types; resume completes existing ops only.
- No cross-turn memory beyond the single active pending record per phone.
- No change to the chat widget, channels, auth, or multi-tenant infra.

## Open architectural questions

- **A-Q3.** Idempotency check: an `op_token` column on the sale, or an in-process committed-token set? Fallback: in-process set keyed by phone for v1, a column when #63 lands durability.
- **A-Q4.** Should resume serve ADD_STOCK paused on quantity? Fallback: sale-needs-price and product-needs-name only.

## Source

Spec context: ./context.md.
