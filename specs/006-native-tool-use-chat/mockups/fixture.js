// Beans & Co native-tool-use chat mockup (spec 006).
// Realistic Beans fixtures plus a state-machine driver. No frameworks, no fetch.
// Everything here is local mutation so Dario can click and see the surface breathe.

export const fixtures = {
  stockAnswer: "Te quedan 48 Pulsera Cafe Clasica (PCC-001) en stock.",
  proposeSale: {
    op: "Registrar venta",
    kv: [
      ["Producto", "Pulsera Cafe Tostado (PCT-002)"],
      ["Cantidad", "3"],
      ["Total", "10.500"],
    ],
    receipt: {
      title: "Venta registrada",
      detail: "Pulsera Cafe Tostado por 10.500",
      balance: "Saldo del dia: 128.400",
      tile: "Ventas",
      undo: true,
      irreversible: false,
    },
  },
  proposeExpense: {
    op: "Registrar gasto",
    kv: [
      ["Concepto", "Envio a Costa Rica"],
      ["Monto", "7.200"],
    ],
    receipt: {
      title: "Gasto registrado",
      detail: "Envio a Costa Rica por 7.200",
      balance: "Saldo del dia: 121.200",
      tile: "Resultado",
      undo: true,
      irreversible: false,
    },
  },
  proposeBatch: {
    op: "Cargar stock de varios productos",
    items: [
      ["1. Pulsera Cafe Clasica x12", "PCC-001"],
      ["2. Pulsera Cafe Miel x8", "PCM-003"],
      ["3. Pulsera Cafe Tostado x6", "PCT-002"],
    ],
    subtotal: ["Total a ingresar", "26 unidades"],
    receipt: {
      title: "Stock cargado",
      detail: "26 unidades en 3 productos",
      balance: "Stock total: 312 unidades",
      tile: "Stock",
      undo: false,
      irreversible: false,
    },
  },
  proposeCancel: {
    op: "Cancelar ultima venta",
    kv: [
      ["Venta", "Pulsera Cafe Tostado x3"],
      ["Total", "10.500"],
      ["Fecha", "hoy 14:22"],
    ],
    irreversible: true,
    receipt: {
      title: "Venta cancelada",
      detail: "Se repuso el stock de Pulsera Cafe Tostado",
      balance: "Saldo del dia: 117.900",
      tile: "Ventas",
      undo: false,
      irreversible: true,
    },
  },
  error: {
    text: "No reconoci el producto. Decime el nombre exacto o el codigo.",
    incident: "ref 7f3a",
  },
  conversation: [
    { who: "user", text: "cuanto facture hoy" },
    { who: "assistant", text: "Hoy llevas 138.900 en ventas pagas, 11 ventas." },
    { who: "user", text: "y cuanto stock de la clasica" },
    { who: "assistant", text: "Te quedan 48 Pulsera Cafe Clasica (PCC-001)." },
    { who: "user", text: "vendi 3 tostado" },
  ],
};

const chips = [
  "Vendi 3 pulseras tostado",
  "Gaste 7.200 en envios",
  "Como venimos hoy",
];

function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
}

function bubble(who, text) {
  const row = el("div", "tim-row " + who);
  row.appendChild(el("div", "bubble " + who, text));
  return row;
}

function working() {
  const w = el("div", "tim-working");
  w.setAttribute("role", "status");
  w.setAttribute("aria-live", "polite");
  w.innerHTML = 'Trabajando <span class="dots"><i></i><i></i><i></i></span>';
  return w;
}

function receiptCard(r) {
  const c = el("div", "tim-receipt settle");
  c.setAttribute("role", "status");
  let actions = `<a class="nav-link" href="#" data-noop>Ver en ${r.tile}</a>`;
  if (r.undo) actions += `<button class="btn btn-quiet" data-noop>Deshacer</button>`;
  c.innerHTML = `
    <div class="eyebrow">Registrado</div>
    <div class="done-row"><span class="check">&check;</span><h3>${r.title}</h3></div>
    <div class="detail">${r.detail}</div>
    <div class="balance">${r.balance}</div>
    <div class="receipt-actions">${actions}</div>`;
  return c;
}

function proposeCard(p, onConfirm) {
  const c = el("div", "tim-propose");
  c.setAttribute("role", "group");
  c.setAttribute("aria-label", "Propuesta de operacion");
  let body = "";
  if (p.items) {
    body = '<ul class="tim-items">' +
      p.items.map((it) => `<li><span>${it[0]}</span><span class="v">${it[1]}</span></li>`).join("") +
      "</ul>" +
      `<div class="tim-subtotal"><span>${p.subtotal[0]}</span><span class="v">${p.subtotal[1]}</span></div>`;
  } else {
    body = p.kv.map((r) => `<div class="tim-kv"><span class="k">${r[0]}: </span><span class="v">${r[1]}</span></div>`).join("");
  }
  const irr = p.irreversible ? '<div class="tim-irreversible">No se puede deshacer</div>' : "";
  c.innerHTML = `
    <div class="eyebrow">Propuesta</div>
    <h3>${p.op}</h3>
    ${body}
    ${irr}
    <div class="tim-actions">
      <button class="btn btn-primary" data-confirm>Confirmar</button>
      <button class="btn btn-text" data-cancel>Cancelar</button>
    </div>`;
  const confirmBtn = c.querySelector("[data-confirm]");
  const cancelBtn = c.querySelector("[data-cancel]");
  confirmBtn.addEventListener("click", () => onConfirm(c, p));
  cancelBtn.addEventListener("click", () => {
    const note = bubble("assistant", "Listo, no registre nada.");
    c.replaceWith(note);
  });
  // keyboard: Enter confirms, Escape cancels
  c.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); confirmBtn.click(); }
    if (e.key === "Escape") { e.preventDefault(); cancelBtn.click(); }
  });
  // focus Confirmar on render
  setTimeout(() => confirmBtn.focus(), 30);
  return c;
}

function errorCard(e) {
  const c = el("div", "tim-error");
  c.setAttribute("role", "alert");
  c.innerHTML = `<p>${e.text}</p><div class="tim-incident">${e.incident}</div>`;
  return c;
}

function emptyState(thread, onChip) {
  const wrap = el("div", "tim-empty");
  wrap.innerHTML = `
    <h2>Tu negocio, anotado y al dia.</h2>
    <p>Pedile lo que necesites: stock, ventas, gastos.</p>`;
  const chipWrap = el("div", "tim-chips");
  chips.forEach((t) => {
    const b = el("button", "tim-chip", t);
    b.addEventListener("click", () => onChip(t));
    chipWrap.appendChild(b);
  });
  wrap.appendChild(chipWrap);
  thread.appendChild(wrap);
}

export function mountChat(root) {
  const thread = root.querySelector(".tim-thread");
  const input = root.querySelector(".composer input");
  const sendBtn = root.querySelector(".composer button");

  function clear() { thread.innerHTML = ""; }
  function scroll() { thread.scrollTop = thread.scrollHeight; }
  function add(node) { thread.appendChild(node); scroll(); return node; }

  function onConfirm(card, p) {
    const r = receiptCard(p.receipt);
    card.replaceWith(r);
    r.focus && r.setAttribute("tabindex", "-1");
    scroll();
  }

  function proposeFlow(userText, proposal) {
    clear();
    add(bubble("user", userText));
    const w = add(working());
    setTimeout(() => { w.replaceWith(proposeCard(proposal, onConfirm)); scroll(); }, 650);
  }

  const scenes = {
    empty() { clear(); emptyState(thread, (t) => { input.value = t; runSend(); }); },
    read() {
      clear();
      add(bubble("user", "cuanto stock de la clasica"));
      const w = add(working());
      setTimeout(() => { w.replaceWith(bubble("assistant", fixtures.stockAnswer)); scroll(); }, 600);
    },
    working() { clear(); add(bubble("user", "vendi 3 tostado")); add(working()); },
    sale() { proposeFlow("vendi 3 tostado a 3.500", fixtures.proposeSale); },
    expense() { proposeFlow("gaste 7.200 en envios a costa rica", fixtures.proposeExpense); },
    batch() { proposeFlow("carga stock: 12 clasica, 8 miel, 6 tostado", fixtures.proposeBatch); },
    cancel() { proposeFlow("cancela la ultima venta", fixtures.proposeCancel); },
    error() {
      clear();
      add(bubble("user", "vendi 2 de la que te mostre ayer"));
      const w = add(working());
      setTimeout(() => { w.replaceWith(errorCard(fixtures.error)); scroll(); }, 600);
    },
    conversation() {
      clear();
      fixtures.conversation.forEach((m) => add(bubble(m.who, m.text)));
      const w = add(working());
      setTimeout(() => { w.replaceWith(proposeCard(fixtures.proposeSale, onConfirm)); scroll(); }, 700);
    },
  };

  function runSend() {
    const t = (input.value || "").trim().toLowerCase();
    input.value = "";
    if (/gast|envio/.test(t)) return scenes.expense();
    if (/carg|stock de varios|12/.test(t)) return scenes.batch();
    if (/cancel/.test(t)) return scenes.cancel();
    if (/vend|cobr/.test(t)) return scenes.sale();
    if (/cuant|stock|factur|venimos|como/.test(t)) return scenes.read();
    // default: propose a sale so the core flow is always reachable
    return scenes.sale();
  }

  sendBtn.addEventListener("click", runSend);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") runSend(); });

  return { scenes };
}
