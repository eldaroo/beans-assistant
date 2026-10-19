"""The static Control Center module registry.

One descriptor per business domain. This list is the ONLY contract the status
home knows: adding a Module here (with a ``snapshot`` provider) makes its tile
appear on the home and its items appear in the strip with no edit to the home
route or template (AC1). Removing or reordering is a one-line change here.

M1 registers the three modules sourced from data the platform already holds:
Resultado (net), Inventario, Ventas. Costos, Produccion, Proveedores and
Logistica append themselves here as their milestones (M2 to M5) land; each new
descriptor lights up its tile and rail entry automatically.
"""
from __future__ import annotations

from backend.modules.protocol import Module
from backend.modules.providers import (
    caja_module,
    costos_module,
    logistica_module,
    produccion_module,
    productos_module,
    proveedores_module,
    stock_module,
    ventas_module,
)

# Rail groups match the mockup's left-rail sections (legacy, kept for reversibility).
GROUP_OPERATION = "Operación"

# Owner-facing job TABS of the simplified Command Center (spec 006 AC1). Every
# module declares which tab it lives under via its ``group`` field; the three-tab
# rail is derived from these by ``nav.owner_tabs()`` with no per-module template
# edit. "Hoy" is a synthesized overview tab (all tiles + attention), not a module
# group, so it is not named here.
TAB_HOY = "Hoy"
TAB_OPERACION = "Operación"
TAB_COSTOS = "Costos y producción"

# Stable slug ids per tab label, matching the approved mockup's ``data-tab`` ids
# (specs/006-simplify-command-center/mockups/index.html). Used by the shell to
# key panels and the active-tab highlight. A group value with no entry here falls
# back to a derived accent-stripped slug in ``nav.owner_tabs`` so a brand-new tab
# still renders without a template edit (AC1).
#
# NAMESPACE NOTE (spec 006 T-011): the tab id "costos" is ALSO a module id (the
# Costos module below). The shell beans:navigate router resolves the overlap
# deterministically — a payload with a ``module`` always drills into the module
# page, a bare ``{tab: "costos"}`` switches to the Costos TAB overview — but a new
# tab id must never equal a module id without that router rule in mind.
TAB_IDS = {TAB_HOY: "hoy", TAB_OPERACION: "operacion", TAB_COSTOS: "costos"}

# Left-to-right order of the owner-facing tabs. Hoy is always first (the overview);
# module-group tabs follow in the order the groups first appear in the registry.
TAB_ORDER = [TAB_HOY, TAB_OPERACION, TAB_COSTOS]

_MODULES: "list[Module]" = [
    # Resultado (spec 004 S5 / T-010): repointed from the legacy ?tab=expenses
    # bounce (the mislabel: "Resultado" opened the gastos form) to its own
    # /resultado/{phone} page showing ingresos, gastos, and ganancia.
    Module(
        id="caja",
        label="Resultado",
        route="/resultado/{phone}",
        snapshot=caja_module.snapshot,
        rail_group=GROUP_OPERATION,
        group=TAB_OPERACION,
        order=10,
    ),
    # Productos (spec 004 M-B / S2): the eighth module and the exemplar CRUD
    # surface. Its tile headlines the active product count (one bounded query,
    # fail-open via the home service's degrade path); its dedicated page does
    # full product ABM over products.py. Sits between Resultado and Stock in the
    # rail, matching the approved mockup's left-rail order.
    Module(
        id="productos",
        label="Productos",
        route="/productos/{phone}",
        snapshot=productos_module.snapshot,
        rail_group=GROUP_OPERATION,
        group=TAB_OPERACION,
        order=15,
    ),
    # Stock (spec 004 S3 / T-007): repointed from the legacy ?tab=stock bounce to
    # its own Control Center page. The tile and the low-stock attention item now
    # open /stock/{phone}, so no owner path crosses the brand boundary into
    # /tenants/{phone}.
    Module(
        id="stock",
        label="Stock",
        route="/stock/{phone}",
        snapshot=stock_module.snapshot,
        rail_group=GROUP_OPERATION,
        group=TAB_OPERACION,
        order=20,
    ),
    # Ventas (spec 004 S4 / T-008): repointed from the legacy ?tab=sales bounce
    # to its own /ventas/{phone} page (list, cancel, view-detail, record-sale).
    Module(
        id="ventas",
        label="Ventas semana",
        route="/ventas/{phone}",
        snapshot=ventas_module.snapshot,
        rail_group=GROUP_OPERATION,
        group=TAB_OPERACION,
        order=30,
    ),
    # Costos (spec 003 M2 + M4): the first module with a dedicated page rather
    # than a dashboard tab. Its route is absolute ("/costos/{phone}"); the
    # status-home template resolves an absolute route as-is and substitutes
    # {phone}. The tile headlines the margin of the cheapest complete country
    # (M4, AC9), falling back to the lead country's landed cost when none is
    # complete; the drill-down carries the per-country comparison.
    Module(
        id="costos",
        label="Costos",
        route="/costos/{phone}",
        snapshot=costos_module.snapshot,
        rail_group=GROUP_OPERATION,
        group=TAB_COSTOS,
        order=40,
    ),
    # Produccion (spec 003 M3): units produced this week against the target, with
    # an arrival-cadence-overdue attention item. Its monthly units feed the
    # indirect-allocation denominator the Costos module reads once M4 wires it.
    Module(
        id="produccion",
        label="Producción",
        route="/produccion/{phone}",
        snapshot=produccion_module.snapshot,
        rail_group=GROUP_OPERATION,
        group=TAB_COSTOS,
        order=50,
    ),
    # Logistica (spec 003 M4): shipping + customs per country for the lead
    # bracelet type, with the pending-customs attention signal. Its lanes are the
    # same shipping/customs rows the landed cost reads; this is the dedicated lens.
    Module(
        id="logistica",
        label="Logística",
        route="/logistica/{phone}",
        snapshot=logistica_module.snapshot,
        rail_group=GROUP_OPERATION,
        group=TAB_COSTOS,
        order=60,
    ),
    # Proveedores (spec 003 M5): the active supplier directory with the
    # overdue-check-in attention signal (computed from stored data, no message
    # sent). This is the OWNER's lens; the supplier two-rooms self-service login
    # is M6 behind its named-human gate.
    Module(
        id="proveedores",
        label="Proveedores",
        route="/proveedores/{phone}",
        snapshot=proveedores_module.snapshot,
        rail_group=GROUP_OPERATION,
        group=TAB_COSTOS,
        order=70,
    ),
]


def all_modules() -> "list[Module]":
    """Return the registered modules (a copy, so callers cannot mutate the list)."""
    return list(_MODULES)
