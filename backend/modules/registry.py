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
    proveedores_module,
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
    # Logistica (spec 003 M4): shipping + customs per country for the lead
    # bracelet type, with the pending-customs attention signal. Its lanes are the
    # same shipping/customs rows the landed cost reads; this is the dedicated lens.
    Module(
        id="logistica",
        label="Logística",
        route="/logistica/{phone}",
        snapshot=logistica_module.snapshot,
        rail_group=GROUP_OPERATION,
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
        order=70,
    ),
]


def all_modules() -> "list[Module]":
    """Return the registered modules (a copy, so callers cannot mutate the list)."""
    return list(_MODULES)
