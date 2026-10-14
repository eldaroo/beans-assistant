"""Proveedores module: supplier-directory headline + overdue-check-in attention
(spec 003 M5, T-017 / T-018).

One fetch per render: ``snapshot`` opens a tenant scope, reads the active
supplier directory with each one's check-in status, and derives the tile and the
strip. The tile shows how many active suppliers there are and whether any are
overdue on a check-in; each overdue supplier raises an attention item computed
from stored data, with no message sent (AC13). The supplier two-rooms split (a
supplier never sees margins or another supplier's data) arrives in M6; this
module is the OWNER's lens on the directory.
"""
from __future__ import annotations

from backend.api.tenant_scope import tenant_scope
from backend.modules.protocol import (
    STATUS_EMPTY,
    STATUS_OK,
    AttentionItem,
    Headline,
    ModuleSnapshot,
    Severity,
)
from backend.services.supplier_service import SupplierService

_service = SupplierService()

# Cap the specific overdue signals so a long-neglected directory does not flood
# the strip; beyond the cap collapse to one summarizing item.
MAX_SPECIFIC_OVERDUE = 3

_ROUTE = "/proveedores/{phone}"


def compute_snapshot(directory, phone: str) -> ModuleSnapshot:
    """Build the tile + strip from the supplier directory (a list of
    SupplierStatus; empty for a tenant with no suppliers)."""
    if not directory:
        return ModuleSnapshot(
            headline=Headline(value="0", trend="sin proveedores", trend_tone="flat", status=STATUS_EMPTY),
            attention=[],
        )

    n = len(directory)
    overdue = [s for s in directory if s.is_overdue]
    value = str(n)
    if overdue:
        trend, tone = f"{len(overdue)} sin responder hace tiempo", "warn"
    else:
        trend, tone = "al día", "good"

    if len(overdue) <= MAX_SPECIFIC_OVERDUE:
        attention = [
            AttentionItem(
                severity=Severity.MID,
                text=(
                    f"{s.name} sin check-in hace {s.days_since_checkin} días"
                    if s.days_since_checkin is not None
                    else f"{s.name} sin check-in registrado"
                ),
                action_label="Ver",
                route=_ROUTE,
            )
            for s in overdue
        ]
    else:
        attention = [
            AttentionItem(
                severity=Severity.MID,
                text=f"{len(overdue)} proveedores sin check-in hace tiempo",
                action_label="Ver",
                route=_ROUTE,
            )
        ]

    return ModuleSnapshot(
        headline=Headline(value=value, trend=trend, trend_tone=tone, status=STATUS_OK),
        attention=attention,
    )


def snapshot(phone: str) -> ModuleSnapshot:
    with tenant_scope(phone):
        directory = _service.directory()
    return compute_snapshot(directory, phone)
