# Context packet — Timonel deferred-operation completion (pending multi-turn operations)

`target_kind = existing` · `target_repo = clients/eldaroo/beans-assistant` · `architecture_author = true (mode=update, next ordinal D-007)` · `kaze_attach = false`

Each panelist writes against THIS packet, in their own voice, in their own review file. Hard limit 600 words.

## Raw idea (verbatim)

Timonel deferred-operation completion (pending multi-turn operations) for the Beans&Co assistant. When a write operation pauses to collect a missing required field, Timonel loses the operation. Real transcript Dario hit:

- User: "acabo de vender 40 stanleys"
- Timonel: "Necesito el precio de venta de Termos Stanley antes de cobrar. ¿A cuánto la vendés?" (Stanley has unit_price=NULL, correct so far)
- User: "32 usd"
- Timonel: "Me falta un dato: el producto" (LOST the product)
- User: "stanleys"
- Timonel: "¿Qué querés hacer con 'stanleys'? ¿Registrar venta, agregar stock, consultar?" (LOST everything)

Confirmed via live prod logs that conversation context IS passed to the router (context length 193 chars on the "32 usd" turn — it included the prior sale and the price question). So this is NOT a memory-storage bug. Two real gaps:

1. The router LLM does not reliably re-extract the pending product/quantity from free-text conversation context.
2. There is no pending-operation state machine. Even if the price were extracted, the current design (UPDATE_PRODUCT_PRICE) would only set the price and would NOT complete the original 40-unit sale, so the user has to re-state it.

DESIRED: a deterministic pending-operation store that, when a write pauses for a missing field, remembers the full operation (e.g. REGISTER_SALE, product=Termos Stanley, quantity=40, missing=[unit_price]); when the user supplies the missing field in a following turn, deterministically fills it AND resumes/completes the original operation (records the 40-unit sale at price 32), rather than re-classifying cold or only setting the price. Generalize beyond sale-needs-price to other paused operations where it is safe.

## Hard constraint (money/sales app)

Completed operations must be correct and idempotent. Never double-record a sale. Never bind to the wrong product or quantity. Handle the user cancelling or changing their mind mid-detour. Handle an ambiguous reply by re-asking, never by guessing. A wrong completed operation is a wrong financial record in a tenant's books.

## Architecture today (the pipeline)

Timonel is a LangGraph pipeline over a shared TypedDict state: `decomposer → router → [read | expander → resolver → write] → final_answer`, with a sub-input loop for multi-intent turns. ARCHITECTURE.md at the repo root carries D-001..D-006 (the flexible-interpretation spec). The new spec is an `update` to that doc starting at D-007.

## Existing code seams (the seed already half-exists)

- `backend/services/chat_service.py`:
  - Class-level in-process history buffer `_history_by_key: dict[str, deque]` (single uvicorn worker; not durable across restarts; the prior spec #63 covers durability and is out of scope here).
  - `_build_message_with_context(phone, message)` — injects "Contexto de conversación reciente: ..." plus an `ambiguity_marker` (when the last assistant turn was AMBIGUOUS) and a `pending_marker` (PR-A fix #3) that names products + pending fields when `last_metadata.pending_entities.items` is set.
  - `_build_pending_entities(operation_type, normalized_entities, missing_fields)` — returns `{operation_type, items:[{name, missing_fields}]}` but ONLY when `missing_fields` is non-empty. The sale-needs-price branch does NOT currently set `missing_fields`, so it produces no pending_entities; quantity is not captured.
  - `_append_history(...)` records the user msg + bot reply + lean metadata (`last_intent`, `operation_type`, `pending_entities`).
  - `chat_with_tenant` is the live web path; it already calls `_build_message_with_context` (via `_invoke_graph`) and `_append_history`. Verified working in prod.
- `agents/router.py`: `classification_to_state`; the multi-turn "Example 3b" (price after a price request → UPDATE_PRODUCT_PRICE); operation types include REGISTER_SALE, UPDATE_PRODUCT_PRICE, REGISTER_PRODUCT, ADD_STOCK, cancels, etc. Router is an LLM (Gemini 2.5 flash) and is the unreliable extraction point.
- `agents/write_agent.py`: the "Necesito el precio de venta de *X* antes de cobrar" branch (around the REGISTER_SALE path) PAUSES the sale when a referenced product has `unit_price_cents IS NULL`. This is where the pending sale is born and currently lost.
- `graph.py`: wiring of nodes + the sub-input loop.

## Related prior spec (complementary, do not duplicate)

`specs/001-timonel-conversational-memory` (issue eldaroo/beans-assistant#63), scoped 2026-05-15, never built, based on a stale master. It covers memory DURABILITY (persistent per-tenant store, restart survival), per-node fault isolation (`safe_node`), typed error codes, and the `inferNavigation` fix. That is complementary infrastructure. THIS spec is the pending-operation resume/complete feature. Reuse #63's `pending_entities` / MemoryStore ideas where sensible; do not re-spec durability.

## Recent shipped context (today, 2026-06-14)

Four fixes already live on master (v107): (1) multi-product create no longer mis-routed as sales; (2) products create with price pending; (3) stable product list order; (4) logged-out page nav redirects to /login. The pending-operation feature builds on top of these.

## The six questions every panelist answers

1. What problem is this actually solving?
2. What is the smallest first version that proves the idea?
3. What 3 risks would kill this if ignored?
4. What does success look like at 90 days?
5. What atomic tasks does this break into? (5-15, each ≤ 1 day)
6. What is the one thing only your faculty would have noticed?
