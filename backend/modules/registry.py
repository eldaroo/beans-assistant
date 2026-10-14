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
    produccion_module,
    stock_module,
    ventas_module,
)

# Rail groups match the mockup's left-rail sections.
GROUP_OPERATION = "Operación"

_MODULES: "list[Module]" = [
    Module(
        id="caja",
        label="Resultado",
        route="?tab=expenses",
        snapshot=caja_module.snapshot,
        rail_group=GROUP_OPERATION,
        order=10,
    ),
    Module(
        id="stock",
        label="Stock",
        route="?tab=stock",
        snapshot=stock_module.snapshot,
        rail_group=GROUP_OPERATION,
        order=20,
    ),
    Module(
        id="ventas",
        label="Ventas semana",
        route="?tab=sales",
        snapshot=ventas_module.snapshot,
        rail_group=GROUP_OPERATION,
        order=30,
    ),
    # Costos (spec 003 M2): the first module with a dedicated page rather than a
    # dashboard tab. Its route is absolute ("/costos/{phone}"); the status-home
    # template resolves an absolute route as-is and substitutes {phone}. The tile
    # shows the lead bracelet type's landed cost with its completeness state; the
    # margin-per-country headline arrives with the multi-country compute in M4.
    Module(
        id="costos",
        label="Costos",
        route="/costos/{phone}",
        snapshot=costos_module.snapshot,
        rail_group=GROUP_OPERATION,
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
        order=50,
    ),
]


def all_modules() -> "list[Module]":
    """Return the registered modules (a copy, so callers cannot mutate the list)."""
    return list(_MODULES)
