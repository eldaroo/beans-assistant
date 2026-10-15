// Fixture data + state driver for the Control Center unification mockup.
// Vanilla ES module, no framework. Realistic Spanish data for Beans and Co.
// The mockup is an implementation-shape seed, not the implementation.

export const TILES = [
  { id: "caja", label: "Resultado", value: "-USD 1.5k", trend: "mes en curso", tone: "warn", group: "Operación" },
  { id: "productos", label: "Productos", value: "4", trend: "activos", tone: "calm", group: "Operación" },
  { id: "stock", label: "Stock", value: "1 u", trend: "1 por agotarse", tone: "warn", group: "Operación" },
  { id: "ventas", label: "Ventas semana", value: "0", trend: "sin ventas aún", tone: "calm", group: "Operación" },
  { id: "costos", label: "Costos", value: "USD 3.10", trend: "costo más bajo", tone: "calm", group: "Operación" },
  { id: "produccion", label: "Producción", value: "0 u", trend: "sin registro", tone: "calm", group: "Operación" },
  { id: "logistica", label: "Logística", value: "vacío", trend: "sin envíos", tone: "calm", group: "Operación" },
  { id: "proveedores", label: "Proveedores", value: "vacío", trend: "sin proveedores", tone: "calm", group: "Operación" },
];

export const ATTENTION = [
  { severity: "warn", text: "Medias verdes con puntillos por agotarse, queda 1 unidad", action: "Ver stock", route: "stock" },
];

// Three volumes for the populated Productos table: 1 / ~50 / ~5000.
const BASE = [
  { sku: "BC-PROD-TERMOS-STANLEY", nombre: "Termos Stanley", desc: "Termo 1L acero", costo: 0, precio: null, estado: "activo" },
  { sku: "BC-PROD-VERDES", nombre: "verdes", desc: "", costo: 0, precio: 4.0, estado: "activo" },
  { sku: "BC-PROD-MEDIAS-PUNTILLISO-VERDES", nombre: "medias verdes con puntillos", desc: "", costo: 0, precio: 3.0, estado: "activo" },
  { sku: "BC-PROD-CAFE-MOLIDO-500", nombre: "Café molido 500g", desc: "Tostado medio", costo: 2.1, precio: 6.5, estado: "activo" },
];

const NOUNS = ["Café en grano", "Café molido", "Termo", "Taza", "Filtro", "Molinillo", "Medias", "Buzo", "Gorra", "Mate"];
const ADJS = ["clásico", "premium", "verde", "negro", "tostado", "orgánico", "edición limitada", "mediano", "grande", "chico"];

function synth(n) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const noun = NOUNS[i % NOUNS.length];
    const adj = ADJS[(i * 7) % ADJS.length];
    const precio = Math.round((2 + ((i * 13) % 40)) * 10) / 10;
    out.push({
      sku: `BC-PROD-${noun.split(" ")[0].toUpperCase()}-${1000 + i}`,
      nombre: `${noun} ${adj}`,
      desc: i % 3 === 0 ? "" : `Lote ${100 + (i % 20)}`,
      costo: Math.round((precio * 0.55) * 100) / 100,
      precio,
      estado: i % 11 === 0 ? "inactivo" : "activo",
    });
  }
  return out;
}

export const VOLUMES = {
  1: BASE.slice(0, 1),
  50: BASE.concat(synth(46)),
  5000: BASE.concat(synth(4996)),
};

export function money(v) {
  if (v === null || v === undefined) return "Sin precio";
  return `$${Number(v).toFixed(2)}`;
}

// State driver: the mockup reads ?state= and ?volume= and ?viewport= and ?theme=
export function readParams() {
  const p = new URLSearchParams(location.search);
  return {
    screen: p.get("screen") || "home",
    state: p.get("state") || "populated",   // empty | loading | populated | error-500 | error-validation | error-403
    volume: Number(p.get("volume") || 50),  // 1 | 50 | 5000
    viewport: p.get("viewport") || "mobile",
    theme: p.get("theme") || "light",
  };
}

export function writeParam(key, val) {
  const p = new URLSearchParams(location.search);
  p.set(key, val);
  history.replaceState(null, "", `?${p.toString()}`);
}
