# Spec: Timonel flexible interpretation and orchestration

## Problem

A shop owner on an empty catalog typed one ordinary Spanish sentence, "vendo medias azules y grises a 5 dolares, y medias multicolor talle s, m y l a 10 dolares", and got two failures: a missing-data ask that named nothing ("Me faltan algunos datos: ese dato, ese dato") and a hard rollback on a SKU collision ("el codigo BC-PROD-MEDIAS-MULTICOLOR ya existe. Ningun producto fue creado"). The owner meant five products: Medias Azules and Medias Grises at five dollars, and Medias Multicolor in talles S, M and L at ten dollars. Timonel has no step that turns a base noun plus a coordinated attribute list plus a shared price into the concrete set of products the owner meant, and when it stumbles it tells the owner nothing useful and rolls back work that was valid. This spec adds that interpretation capability and makes the failure path honest.

## Why now

Beans Assistant is live and onboarding real owners. The empty catalog is the most fragile moment in the product: the owner is deciding in the first minutes whether the tool is worth their time. Conversational variant phrasing ("azules y grises a 5", "talle s, m y l") is the normal way a person loads a catalog, and right now the most common onboarding utterance fails twice in one screen. Every such failure reads as a broken tool and costs an owner.

## Scope

In scope:

- A deterministic attribute-expansion capability: base noun times a color or size list, with the shared price distributed across every expanded product.
- SKU generation that is unique within a single batch and retains the tokens that make variants distinct (colors, single-letter sizes).
- Batch product creation that degrades to partial success and reports per product, replacing the all-or-nothing rollback.
- Missing-field messages that name the product and the field, never a technical index or "ese dato".
- The onboarding conversational copy for the success and failure paths, in Argentine Spanish (voseo), under the voice rule.
- Goldens in tests/eval covering the screenshot input and sibling phrasings.

Out of scope:

- Arbitrary natural-language attribute parsing. Only color lists and size lists in this arc; everything else passes through unchanged.
- Expansion for sales or stock verbs in this arc (REGISTER_PRODUCT and REGISTER_PRODUCT_WITH_STOCK only). See Open questions.
- The chat widget chrome, WhatsApp/Baileys channel, auth, and multi-tenant infrastructure.
- Cross-turn memory of variant sets.

## Whole-problem surface manifest

This is a multi-cohort spec (two milestones). The surfaces it must cover end to end:

```yaml
- id: S1
  surface: attribute expansion - base noun times color/size list into concrete items
- id: S2
  surface: shared-modifier distribution - trailing price applied to every expanded product
- id: S3
  surface: SKU uniqueness within a batch plus discriminating-token retention
- id: S4
  surface: partial-success batch create with honest per-product reporting
- id: S5
  surface: structured missing-field messaging that names product and field
- id: S6
  surface: onboarding conversational copy contract for success and failure paths
- id: S7
  surface: idempotency and reconciliation of an expanded set against catalog state
- id: S8
  surface: ambiguity and overflow guards - bare-number gate and expansion cap
```

## Acceptance criteria

Each criterion is independently verifiable. Surface and trigger named per criterion.

1. **AC1 (S1, S2).** On an empty catalog, sending "vendo medias azules y grises a 5 dolares" creates exactly two products, Medias Azules and Medias Grises, each with `unit_price_cents = 500` and a distinct SKU. Verify: `tests/eval` expansion golden plus the two committed rows.
2. **AC2 (S1, S2, S3).** Sending "vendo medias multicolor talle s, m y l a 10 dolares" creates exactly three products in talles S, M and L, each `unit_price_cents = 1000`, with three distinct SKUs that retain the size token. Verify: golden plus `test_resolver.py::test_sku_keeps_size_token`.
3. **AC3 (S1, S4).** The full screenshot input processed in one turn yields five products; the summary names each created product with its price; the spoken product count equals the committed row count. Verify: `tests/eval/test_attribute_expansion.py::test_screenshot_input`.
4. **AC4 (S5).** No user-facing message contains the literal "ese dato" for an `items[]` miss; a missing per-item field renders as "<Producto>: falta <campo>". Verify: `test_write_agent.py::test_indexed_missing_translates`.
5. **AC5 (S4).** `register_products_batch` lands every valid row and returns a per-item result list; when one of three collides, two land and the message names the two created with their SKUs and the one rejected with its reason, and never says "ningun producto fue creado". Verify: `test_write_agent.py::test_partial_batch_reports_offender`.
6. **AC6 (S8).** The expander fires only when an attribute token is present and there is no bare-number ambiguity; "medias 22, soquetes 15" still routes to AMBIGUOUS, unchanged. Verify: `test_expander.py::test_gate_skips_bare_numbers`.
7. **AC7 (S8).** An expansion that exceeds the per-turn product cap truncates with a message that names the dropped variants; nothing is silently dropped. Verify: `test_expander.py::test_overflow_names_dropped`.
8. **AC8 (S7).** Re-sending the same expanded set within a short window does not duplicate the catalog; the second reply states the variants were already loaded. Verify: `test_write_agent.py::test_resend_no_duplicate`.
9. **AC9 (S1).** The variant vocabulary (colors, sizes) is defined once in `agents/attributes.py` and imported by both the expander and the resolver; no duplicate literal vocabulary lists remain. Verify: grep shows one definition; full suite green.
10. **AC10 (regression).** Read paths and non-REGISTER_PRODUCT write paths bypass the expander unchanged; the existing unit and integration suites stay green. Verify: `tests/integration/test_expander_graph.py` plus the current suites.
11. **AC11 (S6).** Success confirmations follow the copy contract below: they lead with what landed, name each product and price, use voseo, and carry no exclamation marks or emojis. Verify: `test_write_agent.py::test_success_copy_names_products`.

## Conversational contract (in lieu of a visual mockup)

This surface is chat text, not a visual UI, so the contract is the exact bot copy rather than an HTML mockup. These lines, authored by Kaze, are the acceptance copy the implementation must match in shape and order (lead with what landed, name the gap calmly, hand the turn back). Argentine Spanish, voseo.

Before (today):

> No pude cargar nada.
> - vendo medias azules y grises a 5 dolares: Me faltan algunos datos: ese dato, ese dato.

> Operacion fallida: No pude crear los productos: el codigo BC-PROD-MEDIAS-MULTICOLOR ya existe. Ningun producto fue creado. Revisa la lista y volve a intentar.

After (target):

- Two-product expansion:
  > Listo, cargue dos productos a 5 dolares: Medias Azules y Medias Grises. Seguimos con el resto?
- Three-variant expansion:
  > Cargue tres: Medias Multicolor talle S, talle M y talle L, todas a 10 dolares. Va el siguiente?
- Honest partial success on collision:
  > Cargue Medias Multicolor talle S y talle M a 10 dolares. La talle L no entro porque ya tenes una igual cargada. Queres que la saltee o la actualizo?
- Genuine missing data, naming product and field:
  > De las medias azules tengo el color pero me falta el precio. A cuanto las vendes?

## Open questions

- **OQ1 - Where the expansion code runs.** Winston places it in a dedicated node between router and resolver (it is the only place that holds the full sibling set plus the shared modifier before any SKU is generated). Lattice, Amelia and Bob argued for the decomposer, pre-LLM, to avoid a third decider of "is this multiple products" fighting the router AMBIGUOUS path. The spec proceeds with Winston's node as the chosen path (D-001) and treats the decomposer placement as the logged alternative. Answer owner: Winston plus Amelia at /develop M1. Default if unanswered: ship the node.
- **OQ2 - Idempotency on resend (Mar'ah).** There is no idempotency key today. A retry of a half-landed batch can double-create. Answer owner: Dario. Default the spec proceeds with: dedupe a retry by product name within the owner's catalog inside a short window (AC8).
- **OQ3 - Should expansion serve sales too** ("vendi 5 medias azules y grises")? Answer owner: Dario. Default: REGISTER_PRODUCT only this arc; keep the expander general enough to extend.
- **OQ4 - Shared-price confirmation threshold.** Above how many expanded products should the bot echo the distributed price back and wait for assent before committing? Answer owner: Dario. Default: echo always in the summary; require assent only above five expanded products.

## Panelists who contributed

- **Winston** (BuildOS Architect, architecture-author) - the expander-as-node decision and the SKU and batch contracts.
- **Amelia** (Senior Dev) - the implementation seams, the `apply_variant_hint` short-circuit hazard, the full-graph verification requirement.
- **Bob** (Scrum Master) - the milestone sequencing and the "smallest first version proves the screenshot" framing.
- **Kaze** (Creative Director) - the conversational copy contract and the rhythm-of-the-apology cut.
- **Lattice** (Structural Integrity) - the single-vocabulary invariant, the bare-number gate, the overflow cap, and "one writer per fact".
- **Mar'ah** (Truth gate) - the summary-from-returned-rows requirement, partial-success honesty, and the idempotency open question.
