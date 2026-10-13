"""Service layer for the costing module (spec 003 M2).

Computes a landed cost per bracelet type per country as the sum of six
components (materials, labor, packaging, shipping, customs, indirect). Each
component is either filled (a USD-cents amount) or pending (unknown yet). A
pending component is never summed as zero; it is named and the result carries a
completeness state (D-016). The pure ``recompute`` core serves both the stored
build and the read-only assistant scenario path (D-022 / AC10, consumed in M5):
``recompute(components, overrides)`` applies a hypothetical without writing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.repositories.costing_repository import CostingRepository

STATUS_COMPLETE = "completo"
STATUS_PARTIAL = "parcial"

# The six components in render order; the Spanish labels are owned here (never in
# the template or the shell), matching the frozen costing mockup.
COMPONENT_ORDER = [
    ("materials", "Materiales"),
    ("labor", "Mano de obra"),
    ("packaging", "Empaque"),
    ("shipping", "Envío"),
    ("customs", "Aduana"),
    ("indirect", "Indirectos"),
]
TOTAL_COMPONENTS = len(COMPONENT_ORDER)  # 6


@dataclass(frozen=True)
class CostComponent:
    """One line of the landed cost. ``cents`` is None when the component is
    pending — unknown yet, excluded from the total, never treated as zero."""

    key: str
    label: str
    cents: Optional[int]
    detail: str = ""

    @property
    def is_filled(self) -> bool:
        return self.cents is not None


@dataclass(frozen=True)
class LandedCost:
    product_id: int
    product_name: str
    country: str
    components: list      # list[CostComponent], render order, length TOTAL_COMPONENTS
    total_cents: int      # sum of filled components only
    status: str           # completo | parcial
    pending_labels: list  # labels of the pending components

    @property
    def is_complete(self) -> bool:
        return self.status == STATUS_COMPLETE

    @property
    def filled_count(self) -> int:
        return sum(1 for c in self.components if c.is_filled)


def recompute(components, overrides=None):
    """Pure landed-cost core.

    Sum the filled components; a pending component (cents is None) is excluded,
    never summed as zero. ``overrides`` maps a component key to a cents value, or
    to None to force that component pending — this is the read-only scenario path
    (D-022). The input list is not mutated. Returns
    ``(resolved_components, total_cents, status, pending_labels)``.
    """
    overrides = overrides or {}
    resolved = []
    total = 0
    pending = []
    for c in components:
        cents = overrides[c.key] if c.key in overrides else c.cents
        rc = CostComponent(key=c.key, label=c.label, cents=cents, detail=c.detail)
        resolved.append(rc)
        if rc.is_filled:
            total += int(rc.cents)
        else:
            pending.append(rc.label)
    status = STATUS_COMPLETE if not pending else STATUS_PARTIAL
    return resolved, total, status, pending


def _as_cents(value):
    return None if value is None else int(round(float(value)))


class CostingService:
    """Orchestrates the costing repository and the landed-cost computation."""

    def __init__(self, repository: CostingRepository | None = None):
        self.repository = repository or CostingRepository()

    def _materials(self, product_id, country):
        """Materials via the BOM: sum of each line's quantity times that input's
        latest USD unit cost. If any BOM input is unpriced the component is
        pending (named), never summed as zero."""
        rows = self.repository.materials_breakdown(product_id, country)
        if not rows:
            return None, "sin receta (BOM) cargada"
        missing = [r["name"] for r in rows if r["unit_usd_cents"] is None]
        if missing:
            return None, "falta precio de: " + ", ".join(missing)
        total = sum(float(r["quantity"]) * float(r["unit_usd_cents"]) for r in rows)
        return int(round(total)), ", ".join(r["name"] for r in rows)

    def build_components(self, product_id, country):
        """Read every component for (product, country); return the six
        CostComponents in render order, some possibly pending."""
        repo = self.repository

        materials_cents, materials_detail = self._materials(product_id, country)

        lab = repo.labor_cost(product_id, country)
        if lab and lab["units_completed"]:
            labor_cents = int(round(float(lab["batch_payment_cents"]) / float(lab["units_completed"])))
            labor_detail = f"por unidad, lote de {int(lab['units_completed'])}"
        else:
            labor_cents, labor_detail = None, "sin lote registrado"

        pack = repo.packaging_cost(product_id, country)
        packaging_cents = _as_cents(pack["usd_amount_cents"]) if pack else None
        packaging_detail = "por unidad" if packaging_cents is not None else "sin empaque cargado"

        ship = repo.shipping_lane(product_id, country)
        shipping_cents = _as_cents(ship["usd_amount_cents"]) if ship and ship["usd_amount_cents"] is not None else None
        shipping_detail = (ship["note"] if ship and ship["note"] else "por averiguar")

        cust = repo.customs_duty(product_id, country)
        customs_cents = _as_cents(cust["usd_amount_cents"]) if cust and cust["usd_amount_cents"] is not None else None
        customs_detail = (cust["note"] if cust and cust["note"] else "por averiguar")

        ind = repo.indirect_latest(country)
        if ind and ind["units_produced"]:
            indirect_cents = int(round(float(ind["pool_cents"]) / float(ind["units_produced"])))
            indirect_detail = f"exhibidores + overhead, {ind['period_month']}"
        else:
            indirect_cents, indirect_detail = None, "sin producción registrada este mes"

        by_key = {
            "materials": CostComponent("materials", "Materiales", materials_cents, materials_detail),
            "labor": CostComponent("labor", "Mano de obra", labor_cents, labor_detail),
            "packaging": CostComponent("packaging", "Empaque", packaging_cents, packaging_detail),
            "shipping": CostComponent("shipping", "Envío", shipping_cents, shipping_detail),
            "customs": CostComponent("customs", "Aduana", customs_cents, customs_detail),
            "indirect": CostComponent("indirect", "Indirectos", indirect_cents, indirect_detail),
        }
        return [by_key[key] for key, _ in COMPONENT_ORDER]

    def landed_cost(self, product_id, country, overrides=None) -> LandedCost:
        """AC8: the landed cost for one bracelet type in one country, as the sum
        of the filled components, carrying the completeness state."""
        prod = self.repository.product(product_id)
        product_name = prod["name"] if prod else str(product_id)
        components = self.build_components(product_id, country)
        resolved, total, status, pending = recompute(components, overrides)
        return LandedCost(
            product_id=product_id,
            product_name=product_name,
            country=country,
            components=resolved,
            total_cents=total,
            status=status,
            pending_labels=pending,
        )

    def lead_landed_cost(self, overrides=None) -> Optional[LandedCost]:
        """The lead bracelet type and its first country, for the home tile and the
        default drill-down. None when no costing data exists yet."""
        types = self.repository.list_bracelet_types()
        if not types:
            return None
        lead = types[0]
        countries = self.repository.countries_for(lead["id"])
        if not countries:
            return None
        return self.landed_cost(lead["id"], countries[0], overrides)
