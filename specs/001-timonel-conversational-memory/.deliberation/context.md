# Context packet — timonel-conversational-memory

**Run id:** timonel-conversational-memory-20260515-182140
**Source:** inline (not from `future_projects.yaml`)
**Target repo:** `clients/eldaroo/beans-assistant/` (`target_kind = existing`)
**Worktree:** `clients/eldaroo/.worktrees/beans-assistant--spec-timonel-memory/`
**Default branch in repo:** `master`

---

## Raw idea (verbatim from Dario)

> preciso que timonel tenga memoria, y pueda analizar mensajes actuales en funcion a pasados, tambien fijate porque creo q crasheo

A screenshot was attached. Decoded transcript of the Timonel chat widget shown:

| Turn | Role | Message |
|------|------|---------|
| 1 | user | ¿Qué productos están por agotarse? |
| 1 | bot  | No hay productos en el inventario. |
| 2 | user | agreguemos |
| 2 | bot  | ¿Qué querés agregar: una venta, un gasto, un producto nuevo o stock? |
| 2 | side-effect | UI flips to "Gastos abierto. Volvé al chat con el botón de arriba." |
| 3 | user | un prodcuo al inventario  *(typo: "prodcuo" for "producto")* |
| 3 | bot  | No pude procesar tu mensaje ahora. Probá de nuevo en un momento. |

Two distinct bug surfaces:
- Turn 2 picked **Gastos** as the side-effect of "agreguemos" *while also* asking the disambiguation question. Action and clarification fired together. Memory of turn 1 (where the user already named the topic — **products** running out) should have collapsed the ambiguity in favor of REGISTER_PRODUCT or ADD_STOCK.
- Turn 3 hit the generic LLM-unavailable / dispatcher-fallback copy. Likely a downstream exception in the resolver or write_agent, masked by the front-end's `ERROR_FALLBACK_COPY['llm_unavailable']` or by an upstream `error` field set without being surfaced.

---

## What "Timonel" is in this codebase

Timonel is the **decomposer** LangGraph node added on 2026-05-08 (commit `02743b7`, PR #36). It sits at the entry of the graph:

```
user_input -> decomposer (Timonel) -> router -> resolver -> [read_agent | write_agent] -> final_answer
                              |                                         |
                              +-- if multi-intent, splits into          +-- sub_input_advancer loops
                                  sub_input_queue and runs each             through the queue
                                  sub_input through the router
```

`agents/decomposer.py`:
- Pure-regex `should_decompose()` gate (`LIST_SEPARATOR` for 3+ items, `MULTI_VERB` for 2+ distinct action verbs).
- Pass-through with zero LLM cost on single-intent inputs.
- Pydantic `DecomposerOutput` + `DECOMPOSER_PROMPT` for the multi-intent split.
- Hard cap `MAX_SUB_INPUTS = 10`.
- Helpers `_advance_sub_input` and `flush_sub_input_result`.

`agents/state.py` `AgentState`:
- Core: `messages` (annotated `add_messages`), `user_input`, `phone`, `sender`.
- Intent: `intent`, `operation_type`, `confidence`, `missing_fields`.
- Resolution: `normalized_entities`.
- Results: `sql_result`, `operation_result`, `final_answer`, `error`.
- Flow: `next_action`, `metadata` (used by Timonel for the sub-input queue).

`agents/router.py` already has an "IMPORTANT CONVERSATION CONTEXT" section in its prompt that expects the user input to optionally be prefixed with `Contexto de conversación reciente:`. So the router is downstream-ready; the upstream wiring is what is partial.

---

## Current memory implementation (the partial it stops at today)

`backend/services/chat_service.py` `ChatService` keeps an **in-process per-phone deque**:

- Class-level `_history_by_key: dict[str, deque]` keyed by `f"phone:{phone}"`.
- `maxlen = CHAT_CONTEXT_MAX_TURNS * 2` (default 6 turns × 2 messages = 12 entries).
- TTL `CHAT_CONTEXT_TTL_SECONDS = 1800` (30 min); older history is evicted on next read.
- `_build_message_with_context()` renders the deque into a `Contexto de conversación reciente:` block plus two markers:
  - `[Nota: el turno anterior del asistente fue una pregunta de aclaracion entre dos intents...]` when the prior assistant turn's `metadata.last_intent == "AMBIGUOUS"`.
  - `[Contexto: turno anterior pidio <fields> para los productos: <names>...]` when the prior turn left `pending_entities.items` set (PR-A fix).
- The contextualized string replaces the raw user message before calling `create_business_agent_graph().invoke(...)`.

What this means in practice:

1. Memory exists for the WEB widget surface only, scoped to the FastAPI process.
2. Memory is **lost on every container restart**. The Nomad alloc has restarted multiple times; the live whatsapp connector restarted yesterday from a template re-render. Each restart wipes every conversation everywhere.
3. WhatsApp (Baileys connector) goes through a separate dispatcher path. Whether it shares this deque depends on whether messages are routed through the same `ChatService` — needs verification by the panel.
4. Timonel (the decomposer) reads `state.user_input` directly. It does not consult the deque. So the decomposer's regex gate runs on the contextualized prompt only because chat_service prepended the context — Timonel itself has no notion of conversation history.
5. There is no episodic store, no embedding-based retrieval, no per-tenant fact memory, no cross-channel persistence.

---

## Stack and surface context

- **Repo:** `eldaroo/beans-assistant`, branch `master`, latest commit `02743b7`.
- **Languages:** Python 3.10+ (FastAPI + LangGraph), Node (Baileys WhatsApp connector at `whatsapp_baileys/`).
- **Storage:** SQLite default. Postgres available via `USE_POSTGRES=true` (currently `true` in production). Redis available, currently disabled (`REDIS_ENABLED=false`).
- **LLM:** Anthropic Claude as principal, Gemini 2.5 Flash as fallback, OpenAI optional.
- **Multi-tenancy:** isolated databases per tenant phone, `data/clients/<phone>/business.db` + `config.json`. Memory must respect this boundary.
- **Surfaces:** web chat widget (`backend/static/js/chat_widget.js`) embedded in `tenant_detail.html` and `onboarding.html`, plus the Baileys WhatsApp connector.
- **Production deployment:** three Nomad jobs (`beans-assistant`, `beans-assistant-tenants`, `beans-assistant-whatsapp`), all on vmi3022858. Backend `/health` currently reports `whatsapp:unhealthy` because the consul-template fix landed in `Light-Brands/infrastructure#40` is not yet deployed.

---

## What the panel is being asked to deliver

Each panelist writes one review file at `_qie/specs/_panel-runs/timonel-conversational-memory-20260515-182140/reviews/<panelist>-review.md`, ≤ 600 words, answering the same six prompts:

1. What problem is this actually solving?
2. What is the smallest first version that proves the idea?
3. What 3 risks would kill this if ignored?
4. What does success look like at 90 days?
5. What atomic tasks does this break into? (5-15 items, each ≤ 1 day of work)
6. What is the one thing only your faculty would have noticed?

The synthesis you contribute to has two halves:
- **Memory feature**: a real, persistent, multi-tenant-safe conversational memory that Timonel and the router can consult.
- **Crash investigation**: root-cause and bound-fix for the "No pude procesar tu mensaje ahora" path that fired on a typo'd input.

Both halves can land as one spec because the crash is plausibly a symptom of the same gap (no history-aware fallback, no graceful degradation when a single agent step throws).
