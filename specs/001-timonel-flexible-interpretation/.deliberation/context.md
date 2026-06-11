# Context packet — Timonel flexible interpretation and orchestration

Run id: `timonel-flexible-interpretation-20260611-121645`
Target repo: `clients/eldaroo/beans-assistant` (GitHub `eldaroo/beans-assistant`), `target_kind = existing`.
Working branch: `claude/spec-timonel-flexible-interpretation`.

Each panelist writes against THIS packet, in their own voice, in their own review file under `reviews/`. Six questions, 600-word limit.

## The raw idea (verbatim from Dario)

"estamos trabajando en beans assistant. Necesitamos hacer una mejora sustancial en la capacidad de interpretacion y orquestacion de Timonel. Mira como se comporta actualmente [screenshot] /develop --headless el fix para hacerlo mucho mas flexible, hacelo con ayuda del team"

Translation: substantial improvement to Timonel's interpretation and orchestration capability. Make it much more flexible.

## What Timonel is

Timonel ("helmsman") is the LangGraph multi-agent business assistant inside Beans Assistant (a.k.a. "Bitácora AI"), a tool that lets small shop owners run their business in natural Spanish from a chat widget. Owners load products into a catalog and register sales, expenses, and stock. The system is LIVE on a Nomad cluster.

Pipeline (per turn), all in `clients/eldaroo/beans-assistant/`:

```
decomposer -> router -> [read_agent | resolver -> write_agent -> read_agent?] -> final_answer
                                                                    -> sub_input_advancer? -> router (next sub-input)
                                                                    -> END
```

- `agents/decomposer.py` — pre-LLM regex gate (LIST_SEPARATOR or 2+ ACTION_VERBS) decides if a message is multi-intent. If so a cheap LLM splits it into self-contained sub-inputs seeded into `metadata.sub_input_queue`. Single-intent passes through with zero LLM. MAX_SUB_INPUTS = 10.
- `agents/router.py` — one LLM classifies intent (READ_ANALYTICS / WRITE_OPERATION / MIXED / GREETING / AMBIGUOUS / DECLINE_PRODUCT_CREATION) and operation_type (REGISTER_SALE / REGISTER_EXPENSE / REGISTER_PRODUCT / REGISTER_PRODUCT_WITH_STOCK / UPDATE_PRODUCT_PRICE / ADD_STOCK / cancels / DEACTIVATE_PRODUCT). It extracts `normalized_entities` and `missing_fields`. REGISTER_PRODUCT supports a multi-product `items: [{name, unit_price?, sku?}]` shape. Long, heavily exampled system prompt.
- `agents/resolver.py` — resolves product references to product_id (fuzzy + LLM disambiguation), normalizes dates, converts price USD->cents, validates required fields per operation, autogenerates SKUs via `generate_sku_from_name`. ~1130 lines.
- `agents/write_agent.py` — non-LLM executor. Calls `database_config` functions (`register_sale`, `register_product`, `register_products_batch`, `add_stock`, etc). Builds the Spanish summary. Batch product create is atomic (all rows land or none).
- `graph.py` — wires the LangGraph, owns `final_answer` (translates missing_fields to Spanish, builds the aggregated multi-sub-input summary), and the sub-input loop.
- `database_config.py` — DB helpers including `register_products_batch` (atomic).

The architecture overview (now archived) is at `root_archive/ARCHITECTURE.md`. There is NO live `ARCHITECTURE.md` at the repo root; this spec authors one.

## The failure under test (real screenshot, empty-catalog onboarding)

Onboarding greeting fired ("Veo que estas arrancando con el catalogo vacio. Querés que carguemos los primeros productos juntos?"). The owner answered, was asked for price, then typed:

> "vendo medias azules y grises a 5 dolares, y medias multicolor talle s, m y l a 10 dolares"

Timonel produced two visible failures:

1. For "vendo medias azules y grises a 5 dolares" it replied:
   "No pude cargar nada. - vendo medias azules y grises a 5 dolares: Me faltan algunos datos: • ese dato • ese dato. ¿Me los podés decir?"
2. For "vendo medias multicolor talle s, m y l a 10 dolares" it replied:
   "Operación fallida: No pude crear los productos: el código 'BC-PROD-MEDIAS-MULTICOLOR' ya existe. Ningún producto fue creado. Revisá la lista y volvé a intentar."

## Root causes (already traced in the code)

**RC1 — No attribute expansion.** A real owner says one noun plus a list of variant attributes plus a shared price: "medias azules y grises a 5 dolares" means TWO products (Medias Azules, Medias Grises) at $5 each; "medias multicolor talle s, m y l a 10 dolares" means THREE size variants (talle S, M, L) at $10 each. Timonel has no general "base noun + variant list -> cartesian set of concrete products, each inheriting the shared modifiers (price)" capability. The decomposer splits on commas/`y` but does not distribute a shared noun across a coordinated attribute list, and does not distribute a trailing shared price across the expanded set. The router multi-product `items` shape exists but is not reliably populated from this phrasing.

**RC2 — "ese dato" leak.** When the multi-product validation finds missing per-item fields it appends indexed technical names like `items[0].name`. The Spanish translation tables in `graph.py:_compute_per_sub_input_answer` and `write_agent.py` only translate flat field names, so indexed names hit the generic fallback "ese dato". The owner is told "Me faltan algunos datos: ese dato, ese dato" which names nothing. The message must say WHICH product is missing WHICH field, or (better) the system should have extracted the names in the first place.

**RC3 — SKU collision on batch create.** `generate_sku_from_name` (resolver.py ~898) builds `BC-{TYPE}-{DESC1}-{DESC2}` from the first two descriptor words, skips single-letter tokens, and dedups ONLY against committed DB rows. So "medias multicolor talle s/m/l" all produce the identical base SKU `BC-PROD-MEDIAS-MULTICOLOR` (size token "s/m/l" dropped as single letters; only first two descriptors kept). In a single `register_products_batch` call none of the three exist in the DB yet, so all three get the same SKU, the unique constraint fires on the second insert, and the atomic batch rolls back everything: "Ningún producto fue creado". Need: SKU uniqueness WITHIN a batch (dedupe against in-flight siblings, not just the DB), retention of discriminating tokens (sizes, colors, the words that make variants distinct), and graceful handling when a collision still happens instead of a whole-turn hard fail.

## Scope (from Dario's framing)

In scope: the `agents/` pipeline (decomposer.py, router.py, resolver.py, write_agent.py, graph.py), `database_config` batch helpers, and `tests/eval` goldens. This is a user-facing onboarding surface; the conversational copy obeys Kaze doctrine and Dario's voice rule (plain Spanish, no hype, no emojis, no exclamation marks, honest).

Out of scope (proposed, panel may revise): the chat widget chrome/UI, WhatsApp/Baileys channel, auth, multi-tenant infra, anything outside the interpretation/orchestration path.

## Constraints worth knowing

- Cheap LLM (Haiku-class) is used for decomposer and resolver disambiguation; main LLM for router and read. Adding LLM calls has cost; prefer deterministic expansion where the grammar is regular (color/size lists), LLM where genuinely ambiguous.
- Prices are stored in cents, nullable (a product can be created "precio pendiente").
- Existing design value (root_archive/ARCHITECTURE.md): separation of concerns, no overlapping capabilities, explicit intent classification, stateful TypedDict orchestration.
- The fix ships through /develop --headless after this spec. Tasks become GitHub issues on eldaroo/beans-assistant. Group into milestone cohorts of <=10.

## The six questions (every panelist answers all six, <=600 words)

1. What problem is this actually solving?
2. What is the smallest first version that proves the idea?
3. What 3 risks would kill this if ignored?
4. What does success look like at 90 days?
5. What atomic tasks does this break into? (5-15, each <= 1 day of work, each with a one-line verifiable acceptance)
6. What is the one thing only your faculty would have noticed?
