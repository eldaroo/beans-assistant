"""Logistica module: shipping + customs headline and the pending-customs
attention signal (spec 003 M4, T-016).

One fetch per render: ``snapshot`` opens a tenant scope, reads the lead bracelet
type's logistics lanes across the three countries, and derives the tile and the
strip. The tile shows the cheapest complete logistics cost per unit (shipping
plus customs) or, when none is complete, how many lanes are pending. A lane with
a null customs duty raises a pending-customs attention item, computed from stored
data, never a message (AC8). A null line is excluded, never summed as zero.
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
from backend.services.logistics_service import LogisticsService

_service = LogisticsService()

# Cap the specific pending-lane signals so a fully-unloaded logistics domain does
# not flood the strip; beyond the cap collapse to one summarizing item.
MAX_SPECIFIC_PENDING = 3

_ROUTE = "/logistica/{phone}"


def compute_snapshot(lanes, phone: str) -> ModuleSnapshot:
    """Build the tile + strip from the lead type's logistics lanes (or None)."""
    if lanes is None or not lanes:
        return ModuleSnapshot(
            headline=Headline(value="—", trend="sin logística cargada", trend_tone="flat", status=STATUS_EMPTY),
            attention=[],
        )

    complete = [ln for ln in lanes if ln.is_complete]
    if complete:
        best = min(complete, key=lambda ln: ln.total_cents)
        value = usd_from_cents(best.total_cents)
        trend, tone = f"envío + aduana · {best.country}", "good"
    else:
        pending_count = sum(1 for ln in lanes if not ln.is_complete)
        value = "—"
        trend, tone = f"{pending_count} ruta{'s' if pending_count != 1 else ''} sin costo completo", "warn"

    # Pending-customs signal (AC8): a lane whose customs is pending is the named
    # risk (a duty landing later moves a price decision). Shipping-pending rides
    # as a lower-severity item. Both from stored data, no message sent.
    specific = []
    for ln in lanes:
        if ln.customs_pending:
            specific.append(AttentionItem(
                severity=Severity.MID,
                text=f"Aduana pendiente en {ln.country}",
                action_label="Completar",
                route=_ROUTE,
            ))
    for ln in lanes:
        if ln.shipping_cents is None:
            specific.append(AttentionItem(
                severity=Severity.LOW,
                text=f"Envío pendiente en {ln.country}",
                action_label="Completar",
                route=_ROUTE,
            ))

    if len(specific) <= MAX_SPECIFIC_PENDING:
        attention = specific
    else:
        attention = [AttentionItem(
            severity=Severity.MID,
            text=f"Faltan {len(specific)} costos de logística",
            action_label="Completar",
            route=_ROUTE,
        )]

    return ModuleSnapshot(
        headline=Headline(value=value, trend=trend, trend_tone=tone, status=STATUS_OK),
        attention=attention,
    )


def snapshot(phone: str) -> ModuleSnapshot:
    with tenant_scope(phone):
        lanes = _service.lead_lanes()
    return compute_snapshot(lanes, phone)
