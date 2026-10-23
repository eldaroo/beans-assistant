// COST_SCENARIO read-only recompute path. Ported from backend/services/cost_scenario.py
// (spec 003 M5 / AC10). Answers a hypothetical about landed cost ("y si lo produzco en
// Colombia") by recomputing from STORED facts, writing nothing. Detection + parse are
// DETERMINISTIC (keyword + the business's own types and countries), never an LLM call.

import { landedCost, listBraceletTypes, countriesFor, THREE_COUNTRIES } from "@/lib/domains/costing";

function norm(text: string): string {
  return String(text)
    .toLowerCase()
    .normalize("NFKD")
    .replace(/\p{Mn}/gu, "");
}

const SCENARIO_TRIGGERS = [
  "escenario", "que pasa si", "si muevo", "si produzco", "mover la produc",
  "cuanto costaria", "cuanto saldria", "y si lo hago en", "y si produzco",
];

const COUNTRY_ALIASES: Record<string, string> = {
  colombia: "Colombia",
  armenia: "Armenia-Colombia",
  "armenia-colombia": "Armenia-Colombia",
  "costa rica": "Costa Rica",
  costarica: "Costa Rica",
};

export function isScenario(message: string): boolean {
  const n = norm(message);
  return SCENARIO_TRIGGERS.some((t) => n.includes(t));
}

function detectCountry(message: string): string | null {
  const n = norm(message);
  for (const [alias, canonical] of Object.entries(COUNTRY_ALIASES)) {
    if (n.includes(alias)) return canonical;
  }
  return null;
}

export interface ScenarioResult {
  productId: number;
  productName: string;
  baselineCountry: string;
  scenarioCountry: string;
  baselineTotalCents: number;
  scenarioTotalCents: number;
  deltaCents: number;
  baselineStatus: string;
  scenarioStatus: string;
  moved: boolean;
  bothComplete: boolean;
}

function usd(cents: number): string {
  return `USD ${(cents / 100).toFixed(2)}`;
}

// Read-only entry point. Returns a Spanish reply for a scenario message, or null
// when the message is not an actionable scenario (the normal pipeline handles it).
export async function handleScenario(message: string): Promise<string | null> {
  if (!isScenario(message)) return null;
  const target = detectCountry(message);
  if (target === null) return null;

  const types = await listBraceletTypes();
  if (!types.length) return null;
  const n = norm(message);
  const matched = types.find((t) => n.includes(norm(t.name)));
  const productId = matched ? matched.id : types[0].id;

  const countries = (await countriesFor(productId)) || [];
  const pool = countries.length ? countries : [target];
  const baselineCountry = pool.find((c) => c !== target) ?? pool[0];

  const baseline = await landedCost(productId, baselineCountry);
  const scenario = await landedCost(productId, target);
  const r: ScenarioResult = {
    productId,
    productName: scenario.productName,
    baselineCountry,
    scenarioCountry: target,
    baselineTotalCents: baseline.totalCents,
    scenarioTotalCents: scenario.totalCents,
    deltaCents: scenario.totalCents - baseline.totalCents,
    baselineStatus: baseline.status,
    scenarioStatus: scenario.status,
    moved: baselineCountry !== target,
    bothComplete: baseline.status === "completo" && scenario.status === "completo",
  };
  return formatReply(r);
}

export function formatReply(r: ScenarioResult): string {
  const scenPartial = r.scenarioStatus === "completo" ? "" : " (costo parcial, sube cuando se completen los componentes)";
  if (!r.moved) {
    return `Escenario para ${r.productName} en ${r.scenarioCountry}: costo final ${usd(r.scenarioTotalCents)}${scenPartial}. Es un cálculo sobre los datos cargados; no cambié nada.`;
  }
  const baseFloor = r.baselineStatus === "completo" ? "" : " (parcial, es un piso)";
  if (!r.bothComplete) {
    return `Escenario para ${r.productName}: producir en ${r.scenarioCountry} da un costo final de ${usd(r.scenarioTotalCents)}${scenPartial}, contra ${usd(r.baselineTotalCents)} en ${r.baselineCountry}${baseFloor}. Todavía no puedo comparar con precisión porque falta completar componentes en uno de los dos. Es un cálculo sobre los datos cargados; no cambié nada.`;
  }
  const direction =
    r.deltaCents < 0 ? `baja ${usd(Math.abs(r.deltaCents))}` : r.deltaCents > 0 ? `sube ${usd(r.deltaCents)}` : "queda igual";
  return `Escenario para ${r.productName}: producir en ${r.scenarioCountry} deja el costo final en ${usd(r.scenarioTotalCents)}, contra ${usd(r.baselineTotalCents)} en ${r.baselineCountry} (${direction}). Es un cálculo sobre los datos cargados; no cambié nada.`;
}

export { THREE_COUNTRIES };
