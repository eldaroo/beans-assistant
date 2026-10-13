# Winston review: Beans Control Center reframe

**1. The problem.**
The CEO needs one place to run Beans, not a landed-cost calculator. He opens the platform and must see the state of the business at a glance and what needs his attention today, then drill into any domain. Costing is one of those domains, no longer the whole thing. The real problem is a shell that nucleates production, suppliers, costing, stock, sales, cash, and logistics as uniform modules under a status home, built on a FastAPI and Jinja server-rendered repo that has no component framework to lean on.

**2. Smallest first version.**
The shell plus one real module behind it. Build the module registry, the status home route, the tile grid, and the attention strip. Then wire one existing module end to end: Inventario (Stock), because its data already exists and low coffee stock is the canonical attention item. The home iterates the registry, renders one tile per module from a uniform descriptor, and shows the strip. One real headline number and one real attention rule prove the protocol against live data before the new costing tables exist. Costing plugs in next as the first new module, reusing D-013 to D-016 unchanged.

**3. Three risks.**
- The home couples to every module. If the home template hard-codes each tile, every new module edits the home. The registry plus provider protocol is the guard, and it must land first.
- One slow or broken module takes down the whole home. A synchronous headline query per module is an N-across-modules page load. Each provider must be bounded and fail to a degraded tile, never raise into the page.
- The attention strip becomes noise. With no severity order and no cap, the strip turns into a second to-do list the CEO ignores, the exact failure Dario named.

**4. 90-day success.**
The CEO opens the home every morning and trusts it. All seven domains are registered modules, each showing one honest headline and feeding real attention items. Costing shows cost and margin per country from stored snapshots, and a "¿y si produzco en Colombia?" question is answered in the chat against those numbers. No module edit touches the home.

**5. Atomic tasks.**
1. `backend/modules/registry.py`: Module, Headline, AttentionItem dataclasses, a provider protocol, and the static descriptor list.
2. `backend/services/attention_service.py`: aggregate `module.attention()` across the registry, sort by severity, cap.
3. `backend/api/home.py`: the status home route, default landing.
4. `backend/templates/home.html` plus `_module_tile.html` and `_attention_strip.html`: tile grid and strip macros.
5. Add `headline()` and `attention()` to `backend/services/stock_service.py` and register Inventario.
6. Repeat the two providers for `sales_service.py` and `expenses_service.py`, register them.
7. Extend `backend/services/costing_service.py` with `headline()`, `attention()` (pending component), and register Costos.
8. Add a pure `recompute(snapshot, overrides)` function in `costing_service.py`.
9. Add the read-only COST_SCENARIO Timonel path reading the stored snapshot.
10. Register Producción, Proveedores, and Logística descriptors as those modules land.

**6. The one thing only my faculty noticed.**
This repo has no client component model, so "module" cannot mean a React component you drop in. On FastAPI and Jinja the module boundary is a server-side provider protocol: each module already owns an api, a service, and a repository, so the registry is a thin descriptor that calls the service for a headline and attention, and the home is a template that loops descriptors. The decoupling is a Python protocol, not a frontend framework, and that is what makes the shell cheap to build here and safe to extend.
