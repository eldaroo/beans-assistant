// Realistic Beans&Co fixture data for the Command Center mockup.
// No lorem ipsum, no sensitive real names. ES module.

export const business = "Beans&Co";

export const truth = {
  // the one-sentence daily truth, computed from status (AC3)
  lead: "Hoy entraron 3 ventas por USD 420.",
  focus: "Falta cobrar una (Distribuidora Norte, USD 150).",
  calm: "Lo demás está en orden.",
  empty: "Todavía no hay movimientos hoy. Pedile algo a Timonel para empezar.",
};

export const tiles = {
  hoy: [
    { id:"caja", group:"hoy", label:"Resultado", num:"USD 3.7k", delta:"acumulado, ventas menos gastos", tone:"" },
    { id:"ventas", group:"hoy", label:"Ventas semana", num:"USD 5.2k", delta:"3 ventas, 7 días", tone:"good" },
    { id:"stock", group:"hoy", label:"Stock", num:"103 u", delta:"3 productos bajos", tone:"warn" },
    { id:"productos", group:"hoy", label:"Productos", num:"4", delta:"activos", tone:"" },
  ],
  operacion: [
    { id:"resultado", group:"operacion", label:"Resultado", num:"USD 3.7k", delta:"ingresos USD 5.2k, gastos USD 1.5k", tone:"" },
    { id:"productos", group:"operacion", label:"Productos", num:"4", delta:"activos", tone:"" },
    { id:"stock", group:"operacion", label:"Stock", num:"103 u", delta:"3 bajos", tone:"warn" },
    { id:"ventas", group:"operacion", label:"Ventas", num:"4", delta:"1 pendiente de cobro", tone:"warn" },
  ],
  costos: [
    { id:"costos", group:"costos", label:"Costos", num:"USD 2 +", delta:"costeo parcial, 2 de 6 cargados", tone:"warn" },
    { id:"produccion", group:"costos", label:"Producción", num:"—", delta:"sin producción cargada", tone:"" },
    { id:"logistica", group:"costos", label:"Logística", num:"1", delta:"envío con aduana pendiente", tone:"warn" },
    { id:"proveedores", group:"costos", label:"Proveedores", num:"0", delta:"sin proveedores", tone:"" },
  ],
};

export const attention = [
  { sev:"high", text:"Stock bajo: Termos Alumbrar quedan 0 u", tab:"operacion", module:"stock" },
  { sev:"high", text:"Falta cobrar: Distribuidora Norte, USD 150", tab:"operacion", module:"ventas" },
  { sev:"warn", text:"Envío a Costa Rica con aduana pendiente", tab:"costos", module:"logistica" },
];

export const ventas = [
  { n:"S-1004", cliente:"Distribuidora Norte", estado:"pendiente", total:"USD 150" },
  { n:"S-1003", cliente:"Pedido web", estado:"pagada", total:"USD 92" },
  { n:"S-1002", cliente:"Café del Puerto", estado:"pagada", total:"USD 186" },
  { n:"S-1001", cliente:"Mostrador", estado:"pagada", total:"USD 240" },
];

// Scripted Timonel exchange that demonstrates the trust floor:
// me -> confirm preview -> yes -> receipt + tile flash + change-history.
export const greeting = "Hola. Hoy entraron 3 ventas y falta cobrar una. ¿Qué querés hacer?";

export const chips = [
  "Registrá una venta de 2 termos a 90.000 COP",
  "¿Qué productos están por agotarse?",
  "Cargá un gasto de envío de 25.000 COP",
];

// Deeper modules, so every tile drills into a real view/edit surface (iter-02).
export const proveedores = [
  { nombre:"Café Armenia", contacto:"WhatsApp +57 300 000", checkin:"hace 3 días", estado:"al día" },
  { nombre:"Maderas del Sur", contacto:"maderas@correo.co", checkin:"hace 21 días", estado:"vencido" },
  { nombre:"Hilos y broches CR", contacto:"+506 8000 0000", checkin:"nunca", estado:"sin check-in" },
];
export const produccion = [
  { semana:"2026-W41", producto:"Termos Alumbrar", unidades:120, objetivo:150 },
  { semana:"2026-W41", producto:"Pulseras café", unidades:300, objetivo:280 },
];
export const logistica = [
  { ruta:"Colombia a Costa Rica", estado:"aduana pendiente", eta:"3 días" },
  { ruta:"Armenia a Bogotá", estado:"en tránsito", eta:"1 día" },
];
export const costos = [
  { producto:"Termos Alumbrar", landed:"USD 2.00 +", estado:"parcial, 2 de 6" },
  { producto:"Pulseras café", landed:"USD 0.95", estado:"completo" },
];
export const productos = [
  { nombre:"Pulsera de café clásica", costo:"USD 4.00", precio:"USD 12.00" },
  { nombre:"Pulsera de café dorada", costo:"USD 5.00", precio:"USD 16.00" },
  { nombre:"Termos Alumbrar", costo:"USD 18.00", precio:"USD 39.00" },
  { nombre:"Llavero de café", costo:"USD 2.50", precio:"USD 8.00" },
];
export const stock = [
  { nombre:"Pulsera de café clásica", unidades:97 },
  { nombre:"Termos Alumbrar", unidades:0 },
  { nombre:"Pulsera de café dorada", unidades:3 },
  { nombre:"Llavero de café", unidades:3 },
];

export const scriptedSale = {
  mine: "Registrá una venta de 2 termos a 90.000 COP",
  confirm: {
    q: "¿Registro esta venta?",
    detail: "2 Termos Alumbrar, 90.000 COP, estado pendiente de cobro.",
  },
  receipt: {
    title: "Venta registrada",
    detail: "S-1005, 2 termos, 90.000 COP, pendiente. Toqué Ventas y Stock.",
  },
  flashTiles: ["ventas","stock"],
  history: "Registró venta S-1005 (2 termos, 90.000 COP) desde: \"Registrá una venta de 2 termos a 90.000 COP\".",
};
