"""Timonel COST_SCENARIO read-only recompute path (spec 003 M5, T-019 / AC10).

The assistant can answer a hypothetical about landed cost ("mover la producción
de exhibidores a Colombia") by recomputing from the STORED costing facts without
writing anything. The recompute reuses ``costing_service``'s pure ``recompute``
core through ``landed_cost(..., overrides)`` (D-022): it reads the components,
applies the scenario, and returns the result. No snapshot or costing row is ever
written (AC10). A message that is not a scenario returns None so the normal
assistant pipeline handles it; a scenario whose type/country cannot be identified
returns a plain "could not interpret" reply rather than guessing.

The detection and parse are DETERMINISTIC (keyword + the tenant's own bracelet
types and countries), not an LLM call, so the path is testable and never writes.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Optional

from backend.services.costing_service import THREE_COUNTRIES, CostingService


def _norm(text: str) -> str:
    """Lowercase and strip accents, so 'qué' and 'que' / 'producción' and
    'produccion' match the same deterministic triggers."""
    nfkd = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# Explicit scenario phrasings. Conservative on purpose: the hook only fires on a
# clear hypothetical so it never hijacks a normal read or write.
_SCENARIO_TRIGGERS = [
    "escenario",
    "que pasa si",
    "si muevo",
    "si produzco",
    "mover la produc",
    "cuanto costaria",
    "cuanto saldria",
    "y si lo hago en",
    "y si produzco",
]

# Country aliases -> canonical THREE_COUNTRIES name (accent-stripped keys).
_COUNTRY_ALIASES = {
    "colombia": "Colombia",
    "armenia": "Armenia-Colombia",
    "armenia-colombia": "Armenia-Colombia",
    "costa rica": "Costa Rica",
    "costarica": "Costa Rica",
}


@dataclass(frozen=True)
class ScenarioResult:
    product_id: int
    product_name: str
    baseline_country: str
    scenario_country: str
    baseline_total_cents: int
    scenario_total_cents: int
    delta_cents: int
    baseline_status: str
    scenario_status: str
    moved: bool

    @property
    def both_complete(self) -> bool:
        """A precise sube/baja comparison is only honest when BOTH totals are
        complete; a partial total is a floor, so a delta across a partial side is
        not comparable (the same discipline that refuses a margin off a partial
        cost, applied to the scenario delta)."""
        return self.baseline_status == "completo" and self.scenario_status == "completo"


def is_scenario(message: str) -> bool:
    n = _norm(message)
    return any(trigger in n for trigger in _SCENARIO_TRIGGERS)


def _detect_country(message: str) -> Optional[str]:
    n = _norm(message)
    for alias, canonical in _COUNTRY_ALIASES.items():
        if alias in n:
            return canonical
    return None


def _detect_product(message: str, service: CostingService) -> Optional[int]:
    """Match a bracelet-type name against the message (accent-insensitive
    substring). Falls back to the lead type when no name matches but the tenant
    has a costable type, so 'mover la producción a Colombia' still resolves."""
    n = _norm(message)
    types = service.repository.list_bracelet_types()
    if not types:
        return None
    for t in types:
        if _norm(t["name"]) in n:
            return int(t["id"])
    return int(types[0]["id"])  # lead type


def parse_scenario(message: str, service: CostingService):
    """Return ``(product_id, baseline_country, scenario_country, overrides)`` or
    None when the message is not an actionable scenario. Baseline is the type's
    first country (the status quo); the scenario country is the one named in the
    message. Overrides are empty in v1 (the scenario is a location move); the
    recompute core carries overrides for future phrasings."""
    target = _detect_country(message)
    if target is None:
        return None
    product_id = _detect_product(message, service)
    if product_id is None:
        return None
    countries = service.repository.countries_for(product_id) or [target]
    baseline_country = next((c for c in countries if c != target), countries[0])
    return product_id, baseline_country, target, {}


def run_scenario(service, product_id, baseline_country, scenario_country, overrides=None) -> ScenarioResult:
    """Recompute landed cost for the scenario, reading stored facts, writing
    NOTHING (AC10). Baseline is the current country's landed cost; the scenario is
    the target country's, with any overrides applied through the pure recompute."""
    baseline = service.landed_cost(product_id, baseline_country)
    scenario = service.landed_cost(product_id, scenario_country, overrides)
    return ScenarioResult(
        product_id=product_id,
        product_name=scenario.product_name,
        baseline_country=baseline_country,
        scenario_country=scenario_country,
        baseline_total_cents=baseline.total_cents,
        scenario_total_cents=scenario.total_cents,
        delta_cents=scenario.total_cents - baseline.total_cents,
        baseline_status=baseline.status,
        scenario_status=scenario.status,
        moved=(baseline_country != scenario_country),
    )


def _usd(cents: int) -> str:
    return f"USD {cents / 100:.2f}"


def format_reply(result: ScenarioResult) -> str:
    """A plain-Spanish scenario answer. Names the recompute as a hypothetical over
    stored facts. A sube/baja direction is stated ONLY when both the baseline and
    the scenario cost are complete; otherwise the number is a floor and the reply
    says the comparison is not yet precise (no false-precise delta, council
    Edut/Marcus/Winston)."""
    scen_partial = "" if result.scenario_status == "completo" else " (costo parcial, sube cuando se completen los componentes)"
    if not result.moved:
        return (
            f"Escenario para {result.product_name} en {result.scenario_country}: "
            f"costo final {_usd(result.scenario_total_cents)}{scen_partial}. "
            f"Es un cálculo sobre los datos cargados; no cambié nada."
        )

    base_floor = "" if result.baseline_status == "completo" else " (parcial, es un piso)"
    if not result.both_complete:
        # One or both sides partial: give both figures as floors, no direction.
        return (
            f"Escenario para {result.product_name}: producir en {result.scenario_country} "
            f"da un costo final de {_usd(result.scenario_total_cents)}{scen_partial}, "
            f"contra {_usd(result.baseline_total_cents)} en {result.baseline_country}{base_floor}. "
            f"Todavía no puedo comparar con precisión porque falta completar componentes "
            f"en uno de los dos. Es un cálculo sobre los datos cargados; no cambié nada."
        )

    if result.delta_cents < 0:
        direction = f"baja {_usd(abs(result.delta_cents))}"
    elif result.delta_cents > 0:
        direction = f"sube {_usd(result.delta_cents)}"
    else:
        direction = "queda igual"
    return (
        f"Escenario para {result.product_name}: producir en {result.scenario_country} "
        f"deja el costo final en {_usd(result.scenario_total_cents)}, "
        f"contra {_usd(result.baseline_total_cents)} en {result.baseline_country} "
        f"({direction}). Es un cálculo sobre los datos cargados; no cambié nada."
    )


def handle_message(message: str, service: CostingService | None = None) -> Optional[str]:
    """Deterministic COST_SCENARIO entry point for the assistant (AC10). Returns a
    reply string for a scenario message, or None when the message is not a
    scenario (the normal pipeline then handles it). Reads only, never writes."""
    if not is_scenario(message):
        return None
    service = service or CostingService()
    parsed = parse_scenario(message, service)
    if parsed is None:
        # A scenario trigger fired but no country (and so no actionable cost
        # scenario) was identified. Fall through to the normal pipeline rather
        # than hijacking the turn with costing boilerplate (council Winston MED):
        # a general question like "cuánto costaría contratar a alguien" must not
        # be claimed by the cost-scenario path just because it matched a trigger.
        return None
    product_id, baseline_country, scenario_country, overrides = parsed
    result = run_scenario(service, product_id, baseline_country, scenario_country, overrides)
    return format_reply(result)
