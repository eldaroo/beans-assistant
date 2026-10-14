"""Costos (costing / margin) module: landed-cost headline + pending-component
attention (spec 003 M2).

One fetch per render: ``snapshot`` opens a tenant scope, computes the lead
bracelet type's per-country comparison, and derives the tile and the strip items
from that one result. The tile headlines the margin of the cheapest COMPLETE
country (M4, AC9); when no country is complete it falls back to the lead
country's landed cost rendered parcial with the honesty "+", never a fabricated
margin off a partial cost. A pending component (envío, aduana, ...) raises an
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


# Shipping and customs are the Logistica module's domain (T-016); Costos does not
# re-signal them, so a missing envío/aduana raises exactly one strip item (from
# Logistica), never a duplicate from both modules (council Compass MED).
_LOGISTICS_LABELS = {"Envío", "Aduana"}


def _pending_attention(landed) -> "list[AttentionItem]":
    """Pending-component signal for one country's landed cost, capped so a
    half-loaded cost does not flood the strip (M2 discipline, kept in M4).
    Shipping/customs are excluded here — Logistica owns those signals."""
    pend = [lbl for lbl in landed.pending_labels if lbl not in _LOGISTICS_LABELS]
    if not pend:
        return []
    if len(pend) <= MAX_SPECIFIC_PENDING:
        return [
            AttentionItem(
                severity=Severity.MID,
                text=f"Falta {lbl.lower()} en el costo de {landed.country}",
                action_label="Completar",
                route=_ROUTE,
            )
            for lbl in pend
        ]
    return [
        AttentionItem(
            severity=Severity.MID,
            text=f"Faltan {len(pend)} componentes en el costo de {landed.country}",
            action_label="Completar",
            route=_ROUTE,
        )
    ]


def compute_snapshot(comparison, phone: str) -> ModuleSnapshot:
    """Build the tile + strip from a CountryComparison (or None for no costing data).

    The tile is the margin of the lowest-complete country when one exists (AC9),
    the "cheapest to land and its margin"; otherwise it falls back to the lead
    country's landed cost rendered parcial with the honesty "+" (the M2 tile),
    because a margin is never shown off a partial cost."""
    if comparison is None or not comparison.margins:
        return ModuleSnapshot(
            headline=Headline(value="—", trend="sin costos cargados", trend_tone="flat", status=STATUS_EMPTY),
            attention=[],
        )

    # A real margin needs a COMPLETE landed cost AND a sale price. Filter on
    # margin availability (not just landed completeness), so a complete cost with
    # no price never headlines a fabricated "USD 0" margin (council Edut BLOCKER).
    priced = [m for m in comparison.margins if not m.is_pending]
    complete_landed = [m for m in comparison.margins if m.landed.is_complete]
    attention: "list[AttentionItem]" = []
    if priced:
        # The headline is the margin of the cheapest-to-land country (its sale
        # price assumed in USD — the product price field carries no currency yet,
        # D-M4-3; surfaced on the drill-down and tracked as a follow-up).
        best = min(priced, key=lambda m: m.landed.total_cents)
        value = usd_from_cents(best.margin_cents)
        tone = "good" if best.margin_cents >= 0 else "warn"
        trend = f"margen · {best.country} · precio USD"
    elif complete_landed:
        # Cost is complete but no sale price is set: show the cheapest complete
        # landed COST and say so, never a fabricated margin.
        best = min(complete_landed, key=lambda m: m.landed.total_cents)
        value = usd_from_cents(best.landed.total_cents)
        trend, tone = f"costo · {best.country} · sin precio de venta", "flat"
    else:
        # No country is complete yet: show the lead country's landed cost parcial
        # with the trailing "+" and name what is missing (the M2 behavior).
        lead = comparison.margins[0]
        landed = lead.landed
        value = usd_from_cents(landed.total_cents) + " +"
        faltan = ", ".join(lbl.lower() for lbl in landed.pending_labels)
        trend, tone = f"parcial · falta {faltan}", "warn"
        attention = _pending_attention(landed)

    return ModuleSnapshot(
        headline=Headline(value=value, trend=trend, trend_tone=tone, status=STATUS_OK),
        attention=attention,
    )


def snapshot(phone: str) -> ModuleSnapshot:
    with tenant_scope(phone):
        comparison = _service.lead_comparison()
    return compute_snapshot(comparison, phone)
