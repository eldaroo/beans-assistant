"""Produccion module: units-this-week-vs-target headline + arrival-cadence
attention (spec 003 M3).

``snapshot`` opens a tenant scope, reads the latest recorded week and the overdue
arrivals, and derives the tile and the strip. The tile shows units produced this
week against the target with an honest percent caption; a country whose next
batch is overdue raises an attention item computed from stored data (no message
is sent). The tile feeds the home scorecard the CEO asked for (OQ3 production
number); the monthly units it records are the indirect denominator M4 consumes.
"""
from __future__ import annotations

from backend.api.tenant_scope import tenant_scope
from backend.modules.formatting import units as fmt_units
from backend.modules.protocol import (
    STATUS_EMPTY,
    STATUS_OK,
    AttentionItem,
    Headline,
    ModuleSnapshot,
    Severity,
)
from backend.services.production_service import ProductionService

_service = ProductionService()

# The drill-down route, in the literal {phone} form the registry descriptor uses;
# the status-home href_for macro substitutes {phone} for the tile and the item.
_ROUTE = "/produccion/{phone}"

# More overdue countries than this collapses to one summarizing item so a quiet
# week does not flood the strip with one line per country.
MAX_SPECIFIC_OVERDUE = 2


def compute_snapshot(current, overdue) -> ModuleSnapshot:
    """Build the tile + strip from the current-week status and the overdue list."""
    if current is None:
        headline = Headline(
            value="—", trend="sin producción cargada", trend_tone="flat", status=STATUS_EMPTY
        )
    else:
        value = fmt_units(current.units_produced)
        if current.has_target:
            pct = current.pct_of_target
            trend = f"meta {current.units_target} u · {pct}%"
            tone = "good" if current.meets_target else "warn"
        else:
            trend, tone = "sin meta esta semana", "flat"
        headline = Headline(value=value, trend=trend, trend_tone=tone, status=STATUS_OK)

    overdue = overdue or []
    if not overdue:
        attention = []
    elif len(overdue) <= MAX_SPECIFIC_OVERDUE:
        attention = [
            AttentionItem(
                severity=Severity.MID,
                text=f"Producción atrasada en {s.country}: lote esperado el {s.expected_next_at}",
                action_label="Ver",
                route=_ROUTE,
            )
            for s in overdue
        ]
    else:
        attention = [
            AttentionItem(
                severity=Severity.MID,
                text=f"Producción atrasada en {len(overdue)} países",
                action_label="Ver",
                route=_ROUTE,
            )
        ]

    return ModuleSnapshot(headline=headline, attention=attention)


def snapshot(phone: str) -> ModuleSnapshot:
    with tenant_scope(phone):
        current = _service.current_week()
        overdue = _service.overdue_arrivals()
    return compute_snapshot(current, overdue)
