"""Costos (costing / margin) module: landed-cost headline + pending-component
attention (spec 003 M2).

One fetch per render: ``snapshot`` opens a tenant scope, computes the lead
bracelet type's landed cost for its first country, and derives the tile and the
strip items from that one result. The tile shows the landed cost with its
completeness state; the mockup's margin-per-country headline arrives with the
multi-country compute in M4. A pending component (envío, aduana, ...) raises an
attention item rather than the home rendering a false-precise total (D-016).
"""
from __future__ import annotations

from backend.api.tenant_scope import tenant_scope
from backend.modules.formatting import usd_from_cents
from backend.modules.protocol import (
    STATUS_EMPTY,
    STATUS_OK,
    AttentionItem,
    Headline,
    ModuleSnapshot,
    Severity,
)
from backend.services.costing_service import CostingService

_service = CostingService()

# A costing tenant with more than this many pending components collapses to one
# summarizing attention item, so a half-loaded cost does not flood the strip.
MAX_SPECIFIC_PENDING = 2

# The drill-down route, in the literal {phone} form the registry descriptor uses.
# The status-home template's href_for macro substitutes {phone} for both the tile
# and the attention item, so there is one route convention for this surface.
_ROUTE = "/costos/{phone}"


def compute_snapshot(landed, phone: str) -> ModuleSnapshot:
    """Build the tile + strip from a LandedCost (or None for no costing data)."""
    if landed is None:
        return ModuleSnapshot(
            headline=Headline(value="—", trend="sin costos cargados", trend_tone="flat", status=STATUS_EMPTY),
            attention=[],
        )

    # Honesty treatment (binding mockup rule): a partial total renders with a
    # trailing "+" and names the pending components; a complete total renders clean.
    value = usd_from_cents(landed.total_cents) + ("" if landed.is_complete else " +")
    if landed.is_complete:
        trend, tone = "completo", "good"
    else:
        faltan = ", ".join(lbl.lower() for lbl in landed.pending_labels)
        trend, tone = f"parcial · falta {faltan}", "warn"

    pend = landed.pending_labels
    if not pend:
        attention = []
    elif len(pend) <= MAX_SPECIFIC_PENDING:
        attention = [
            AttentionItem(
                severity=Severity.MID,
                text=f"Falta {lbl.lower()} en el costo de {landed.country}",
                action_label="Completar",
                route=_ROUTE,
            )
            for lbl in pend
        ]
    else:
        attention = [
            AttentionItem(
                severity=Severity.MID,
                text=f"Faltan {len(pend)} componentes en el costo de {landed.country}",
                action_label="Completar",
                route=_ROUTE,
            )
        ]

    return ModuleSnapshot(
        headline=Headline(value=value, trend=trend, trend_tone=tone, status=STATUS_OK),
        attention=attention,
    )


def snapshot(phone: str) -> ModuleSnapshot:
    with tenant_scope(phone):
        landed = _service.lead_landed_cost()
    return compute_snapshot(landed, phone)
