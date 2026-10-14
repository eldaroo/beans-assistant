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
from datetime import date
from typing import Optional

from backend.repositories.costing_repository import CostingRepository
from backend.repositories.production_repository import ProductionRepository

STATUS_COMPLETE = "completo"
STATUS_PARTIAL = "parcial"

# The three countries Beans&Co produces and ships across (spec Problem; the
# mockup's per-country comparison). The margin comparison walks a bracelet type
# across these in this order; a type with no data in a country shows that country
# empty rather than dropping it, so the comparison is always the full set.
THREE_COUNTRIES = ["Colombia", "Armenia-Colombia", "Costa Rica"]

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

# The canonical BOM input categories a bracelet is built from (T-012 breadth).
# Each is a cost_inputs.category; the materials component sums every BOM line
# regardless of category, so adding an input in any of these shows up in the
# total. The Spanish labels are owned here, never in the template.
INPUT_CATEGORIES = [
    ("cafe", "Café"),
    ("tostado", "Tostado"),
    ("madera", "Madera"),
    ("hilo", "Hilo"),
    ("piedras", "Piedras"),
    ("broches", "Broches"),
]


def month_of_iso_week(period_week: str) -> str:
    """Map an ISO ``YYYY-Www`` week to its calendar month ``YYYY-MM`` (AC12).

    A week can straddle two months, so the month is decided by the week's
    Thursday — the ISO-8601 rule that fixes which year/month a week belongs to
    (``date.fromisocalendar(year, week, 4)``). Deterministic at every boundary,
    where "first day of the week" or "last day" would flip a boundary week into
    the wrong month. Raises on a malformed week (the write already normalizes,
    so a bad value here is a real bug, surfaced loud, not a silent mis-attribution)."""
    import re

    m = re.fullmatch(r"(\d{4})-W(\d{1,2})", str(period_week).strip())
    if not m:
        raise ValueError(f"period_week must be ISO 'YYYY-Www': {period_week!r}")
    year, wk = int(m.group(1)), int(m.group(2))
    thursday = date.fromisocalendar(year, wk, 4)
    return thursday.strftime("%Y-%m")


def units_in_month(weekly_rows, period_month: str) -> int:
    """Sum units produced in a calendar month from per-week rows (AC12).

    ``weekly_rows`` is ``[{period_week, units}]`` already deduped to the newest
    record per (country, week) by the repository, so a same-week correction is
    not double-counted. Each week is attributed to its calendar month by its
    Thursday (``month_of_iso_week``); the units of the weeks that fall in
    ``period_month`` are summed. Returns 0 when no week falls in the month, which
    the caller renders as indirect PENDING, never a divide-by-zero."""
    total = 0
    for row in weekly_rows:
        if month_of_iso_week(row["period_week"]) == period_month:
            total += int(row["units"] or 0)
    return total


def labor_per_unit(batch_payment_cents, units_completed):
    """Direct labor per unit on a COMPLETED basis (AC11 / T-013).

    The batch payment is divided by the units actually COMPLETED, not the units
    planned. Marcus: batch labor is a fixed cost masquerading as variable, so a
    short batch (fewer units completed for the same payment) RAISES the per-unit
    labor. Returns USD cents, or None when there is no completed batch to divide
    by (pending, never a divide-by-zero)."""
    if not units_completed:
        return None
    return int(round(float(batch_payment_cents) / float(units_completed)))


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


@dataclass(frozen=True)
class Margin:
    """Margin for one bracelet type in one country (AC9). ``margin_cents`` is None
    when pending — the landed cost is not complete or no sale price is set — and
    ``pending_reason`` names why. A real margin is sale price minus a COMPLETE
    landed total, never computed off a partial cost."""

    country: str
    landed: "LandedCost"
    price_cents: Optional[int]
    margin_cents: Optional[int]
    pending_reason: Optional[str]

    @property
    def is_pending(self) -> bool:
        return self.margin_cents is None


@dataclass(frozen=True)
class CountryComparison:
    """One bracelet type compared across the three countries (AC9). Each entry is
    a Margin carrying its own completeness state. ``lowest_complete_country`` names
    the country with the lowest COMPLETE landed total (the honest "cheapest to
    land"), or None when no country is complete yet (a parcial total never wins)."""

    product_id: int
    product_name: str
    margins: list           # list[Margin], one per country in THREE_COUNTRIES order
    lowest_complete_country: Optional[str]


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

    def __init__(
        self,
        repository: CostingRepository | None = None,
        production: ProductionRepository | None = None,
    ):
        self.repository = repository or CostingRepository()
        # The indirect-allocation denominator is units PRODUCED per country per
        # month, read from production_records (M4 wires Costos to Produccion).
        self.production = production or ProductionRepository()

    def indirect_per_unit(self, country, period_month=None):
        """Indirect cost allocated per unit for a country in a calendar month (AC12).

        The pool (display stands plus overhead) for the country's latest recorded
        month divided by the units PRODUCED in that country that month. Units come
        from production_records, attributed by production period (never by the
        data-entry date, D-M3-9). A month with zero recorded production returns
        pending (None), never a divide-by-zero. Returns ``(cents_or_None, detail)``.
        """
        pool = self.repository.indirect_pool_latest(country)
        if not pool:
            return None, "sin pool indirecto cargado"
        month = period_month or pool["period_month"]
        weekly = self.production.weekly_units(country)
        units = units_in_month(weekly, month)
        if not units:
            return None, f"sin producción registrada en {month}"
        per_unit = int(round(float(pool["pool_cents"]) / float(units)))
        return per_unit, f"exhibidores + overhead, {month} ({units} u)"

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
        labor_cents = labor_per_unit(lab["batch_payment_cents"], lab["units_completed"]) if lab else None
        if labor_cents is not None:
            labor_detail = f"por unidad, lote de {int(lab['units_completed'])}"
        else:
            labor_detail = "sin lote registrado"

        pack = repo.packaging_cost(product_id, country)
        packaging_cents = _as_cents(pack["usd_amount_cents"]) if pack else None
        packaging_detail = "por unidad" if packaging_cents is not None else "sin empaque cargado"

        ship = repo.shipping_lane(product_id, country)
        shipping_cents = _as_cents(ship["usd_amount_cents"]) if ship and ship["usd_amount_cents"] is not None else None
        shipping_detail = (ship["note"] if ship and ship["note"] else "por averiguar")

        cust = repo.customs_duty(product_id, country)
        customs_cents = _as_cents(cust["usd_amount_cents"]) if cust and cust["usd_amount_cents"] is not None else None
        customs_detail = (cust["note"] if cust and cust["note"] else "por averiguar")

        # Indirect allocation (M4, AC12): the pool for the country's latest month
        # divided by units PRODUCED there that month (derived from production_records),
        # not the stale hand-entered units_produced column the M2/M3 read used.
        indirect_cents, indirect_detail = self.indirect_per_unit(country)

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

    def margin(self, product_id, country, overrides=None) -> "Margin":
        """Margin for one bracelet type in one country (AC9).

        Margin is the sale price minus the landed cost. It is a real number ONLY
        when the landed cost is COMPLETE and a sale price is set; otherwise it is
        pending with a named reason. A margin is never computed off a partial
        landed cost (that would be a false-precise figure the honesty treatment
        forbids) and never shown without a price. The sale price is the product's
        ``unit_price_cents`` read as a USD reference price (D-M4-3)."""
        landed = self.landed_cost(product_id, country, overrides)
        price = self.repository.sale_price_cents(product_id)
        if price is None:
            return Margin(country=country, landed=landed, price_cents=None,
                          margin_cents=None, pending_reason="sin precio de venta")
        if not landed.is_complete:
            faltan = ", ".join(lbl.lower() for lbl in landed.pending_labels)
            return Margin(country=country, landed=landed, price_cents=int(price),
                          margin_cents=None, pending_reason=f"costo parcial · falta {faltan}")
        return Margin(country=country, landed=landed, price_cents=int(price),
                      margin_cents=int(price) - landed.total_cents, pending_reason=None)

    def country_comparison(self, product_id, countries=None) -> "CountryComparison":
        """Per-country landed cost and margin for one bracelet type across the
        three countries (AC9). Each country carries its own completeness state;
        the lowest COMPLETE landed total is marked (a parcial total is never the
        winner, because its true total is unknown and could be higher). Returns a
        CountryComparison; ``lowest_complete_country`` is None when no country has
        a complete total yet."""
        countries = countries or THREE_COUNTRIES
        margins = [self.margin(product_id, c) for c in countries]
        complete = [m for m in margins if m.landed.is_complete]
        lowest = min(complete, key=lambda m: m.landed.total_cents).country if complete else None
        # Reuse the product name each margin's landed cost already carries rather
        # than re-fetching products (council Winston LOW: 4 product() calls -> 0 extra).
        product_name = margins[0].landed.product_name if margins else str(product_id)
        return CountryComparison(
            product_id=product_id,
            product_name=product_name,
            margins=margins,
            lowest_complete_country=lowest,
        )

    def lead_comparison(self) -> "Optional[CountryComparison]":
        """The country comparison for the lead bracelet type, for the Costos tile
        and drill-down. None when no costable bracelet type exists yet."""
        types = self.repository.list_bracelet_types()
        if not types:
            return None
        return self.country_comparison(types[0]["id"])

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
