// Timonel operation surface - spec 009 mockup driver.
// Vanilla ES module. Wires local state only (no fetch, no backend).

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// ---- chrome: state / viewport / theme switchers ----
const states = ["populated", "empty", "loading", "error"];
function showState(name) {
  states.forEach((s) => $(`#scroll-${s}`).classList.toggle("hidden", s !== name));
  $$('.chrome [data-state]').forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.state === name)));
  // composer is irrelevant on empty-focus but kept visible; nothing else to do
}
$$('.chrome [data-state]').forEach((b) =>
  b.addEventListener("click", () => showState(b.dataset.state)));

$$('.chrome [data-vp]').forEach((b) =>
  b.addEventListener("click", () => {
    document.body.dataset.vp = b.dataset.vp;
    $$('.chrome [data-vp]').forEach((x) =>
      x.setAttribute("aria-pressed", String(x === b)));
  }));

$$('.chrome [data-theme]').forEach((b) =>
  b.addEventListener("click", () => {
    document.documentElement.dataset.theme = b.dataset.theme;
    $$('.chrome [data-theme]').forEach((x) =>
      x.setAttribute("aria-pressed", String(x === b)));
  }));

// ---- confirm a create/compound/cancel card -> settle to a receipt in place ----
function settle(id, text) {
  const card = $(`#${id}`);
  if (!card || card.dataset.settled === "true") return;
  const receipt = document.createElement("div");
  receipt.className = "receipt";
  receipt.innerHTML =
    `<span class="ok" aria-hidden="true">&check;</span><span>${text}</span>` +
    `<button class="undo-link" data-undo>Deshacer</button>`;
  card.replaceWith(receipt);
  wireUndo(receipt);
}

$$('[data-confirm]').forEach((b) =>
  b.addEventListener("click", () => {
    if (b.dataset.confirm === "compound")
      settle("compound", 'Listo: "pulseras rojas" creada y 50 cargadas al stock.');
    if (b.dataset.confirm === "cancel")
      settle("cancel", "Venta 42 cancelada. 3 unidades volvieron al stock.");
  }));

$$('[data-dismiss]').forEach((b) =>
  b.addEventListener("click", () => {
    const card = $(`#${b.dataset.dismiss}`);
    if (card) card.replaceWith(Object.assign(document.createElement("div"), {
      className: "note", textContent: "Ok, no hice nada.",
    }));
  }));

// ---- disambiguation picker ----
$$('[data-pick]').forEach((opt) =>
  opt.addEventListener("click", () => {
    const group = opt.closest(".card");
    $$('.opt', group).forEach((o) => o.setAttribute("aria-selected", String(o === opt)));
    const pick = opt.dataset.pick;
    const out = document.createElement("div");
    if (pick === "ninguna") {
      out.className = "note";
      out.innerHTML = "Ok. Deci el nombre exacto y lo busco de nuevo.";
    } else {
      out.className = "card";
      out.innerHTML =
        `<div class="eyebrow">Cambiar precio</div>` +
        `<div class="effect">${pick} pasa a $ 350</div>` +
        `<div class="detail">antes estaba a otro precio</div>` +
        `<div class="actions"><button class="btn btn-primary full" id="price-ok">Confirmar</button>` +
        `<button class="btn btn-ghost" id="price-no">Ahora no</button></div>`;
    }
    group.replaceWith(out);
    const ok = $("#price-ok");
    if (ok) ok.addEventListener("click", () => {
      out.replaceWith(Object.assign(document.createElement("div"), {
        className: "receipt",
        innerHTML: `<span class="ok" aria-hidden="true">&check;</span><span>${pick} ahora cuesta $ 350.</span>`,
      }));
    });
    const no = $("#price-no");
    if (no) no.addEventListener("click", () => out.remove());
  }));

// ---- guided cost-flow: advance one field at a time ----
const flowSteps = [
  { q: "Cuanto costo el flete hasta aca, en que moneda?", miss: "Me falta 1 dato para cerrar el costo.",
    tick: "Mano de obra" },
  { q: "Listo. Ya tengo todo para calcular el costo puesto.", miss: "", tick: "Flete", done: true },
];
let flowI = 0;
const flowNext = $("[data-flow-next]");
if (flowNext) flowNext.addEventListener("click", () => {
  const input = $("#flow-input");
  if (input && !input.value.trim()) { input.focus(); return; }
  const list = $("#flow .checklist");
  const step = flowSteps[flowI];
  if (step) {
    const pend = $(".checklist .pend", $("#flow"));
    if (pend) { pend.classList.remove("pend"); pend.innerHTML =
      `<span class="tick" aria-hidden="true">&check;</span> ${step.tick} <span class="meta">&nbsp;cargado</span>`; }
    $("#flow-q").textContent = step.q;
    $("#flow .miss").textContent = step.miss;
    if (input) { input.value = ""; input.focus(); }
    if (step.done) { $("#flow .field").classList.add("hidden"); }
    flowI++;
  }
});

// ---- undo links ----
function wireUndo(scope) {
  $$('[data-undo]', scope).forEach((b) =>
    b.addEventListener("click", () => {
      b.closest(".receipt").replaceWith(Object.assign(document.createElement("div"), {
        className: "note", textContent: "Deshecho. Volvio como estaba.",
      }));
    }));
}
wireUndo(document);

// ---- empty-state examples -> composer ----
$$('[data-example]').forEach((b) =>
  b.addEventListener("click", () => {
    const input = $("#composer-input");
    input.value = b.dataset.example;
    showState("populated");
    input.focus();
  }));

// ---- composer: echo the message (demo only) ----
$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $("#composer-input");
  const text = input.value.trim();
  if (!text) return;
  const scroll = $("#scroll-populated");
  const row = document.createElement("div");
  row.className = "row me";
  row.innerHTML = `<div class="bubble-me"></div>`;
  row.querySelector(".bubble-me").textContent = text;
  scroll.appendChild(row);
  input.value = "";
  scroll.scrollTop = scroll.scrollHeight;
});

// honor ?state= for a direct deep link
const q = new URLSearchParams(location.search).get("state");
if (q && states.includes(q)) showState(q);
