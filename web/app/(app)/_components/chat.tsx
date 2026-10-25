"use client";
// Timonel chat surface (spec 009 M1, mockup specs/009-timonel-operation-surface/mockups).
// Three response shapes as the safety feature (Kaze): an ANSWER is calm and borderless
// with no button; a CREATE card is neutral with an indigo Confirmar; an UNDO/CANCEL is
// amber and deliberate. A product-not-found heals into a compound CREATE card: one card,
// two numbered steps, one Confirmar that creates the product then does the act in order.
// The compound commit is driven by the SAME `driveCompound` the AC3 atomicity test pins
// (tested contract == shipped contract): the step is the unit of commit, and a late-step
// failure leaves the product created with nothing stranded.
import { useRef, useState } from "react";
import { threadProductId, driveCompound, pickedStageArgs } from "@/lib/ops/compound";

type Act = { operationType: string; args: Record<string, unknown>; utterance: string };
type CardState = "pending" | "done" | "undone" | "cancelled";
type CompoundState = "pending" | "done" | "created-only" | "failed" | "cancelled";
type Candidate = { id: number; label: string; detail?: string };

// The destructive and edit ops (spec 009 M3): their card is amber and its confirm button
// carries the verb, so the safety spine is visible, not theater (Kaze, three response
// shapes). Everything else is a neutral create card.
const DESTRUCTIVE_OPS = new Set(["CANCEL_SALE", "CANCEL_EXPENSE", "CANCEL_STOCK", "UPDATE_PRICE", "DEACTIVATE_PRODUCT"]);
function confirmVerb(operation: string): string {
  switch (operation.toUpperCase()) {
    case "CANCEL_SALE":
    case "CANCEL_EXPENSE": return "Cancelar";
    case "CANCEL_STOCK": return "Revertir";
    case "UPDATE_PRICE": return "Cambiar precio";
    case "DEACTIVATE_PRODUCT": return "Desactivar";
    default: return "Confirmar";
  }
}
// The eyebrow names the specific action (the mockup labels each op), not a generic
// "Confirmar accion". A plain Spanish noun per op keeps the card honest about what it does.
function actionLabel(operation: string): string {
  switch (operation.toUpperCase()) {
    case "CANCEL_SALE": return "Cancelar venta";
    case "CANCEL_EXPENSE": return "Cancelar gasto";
    case "CANCEL_STOCK": return "Revertir entrada";
    case "UPDATE_PRICE": return "Cambiar precio";
    case "DEACTIVATE_PRODUCT": return "Desactivar producto";
    default: return "Confirmar accion";
  }
}
// Spanish fallback summary for the destructive/edit ops, so a card whose server consequence
// is somehow absent never shows a raw opType ("CANCEL_SALE"). The normal path always carries
// the consequence; this only guards the degrade case.
function destructiveFallback(operation: string): string {
  switch (operation.toUpperCase()) {
    case "CANCEL_SALE": return "Cancelar la venta indicada.";
    case "CANCEL_EXPENSE": return "Cancelar el gasto indicado.";
    case "CANCEL_STOCK": return "Revertir la entrada de stock indicada.";
    case "UPDATE_PRICE": return "Cambiar el precio del producto indicado.";
    case "DEACTIVATE_PRODUCT": return "Desactivar el producto indicado.";
    default: return "Confirmar la accion.";
  }
}

type Msg =
  | { role: "user"; text: string }
  | { role: "bot"; text: string }
  | { role: "answer"; text: string }
  | { role: "card"; opToken: string; operation: string; preview: unknown; consequence?: string | null; needsConfirm: boolean; reversible: boolean; state: CardState }
  | { role: "disambiguation"; id: string; operation: string; idField: string; pendingArgs: Record<string, unknown>; utterance: string; turnNonce: string; candidates: Candidate[]; chosen: boolean }
  | {
      role: "compound";
      id: string;
      productName: string;
      turnNonce: string;
      step1Token: string;
      act: Act;
      state: CompoundState;
      productId?: number; // set once the product is created, so a failed act can be retried
      note?: string;
    };

async function postJson(url: string, body: unknown) {
  const res = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  return res.json();
}

function summarize(operation: string, preview: unknown): string {
  const p = preview as Record<string, unknown>;
  if (operation === "REGISTER_SALE" && Array.isArray(p?.items)) {
    const it = p.items[0] as Record<string, unknown>;
    return `Venta: ${it?.quantity ?? "?"} x ${it?.productRef ?? it?.productId ?? "?"}${it?.unitPriceCents ? ` a ${(Number(it.unitPriceCents) / 100).toFixed(0)}` : ""}`;
  }
  if (operation === "REGISTER_EXPENSE") return `Gasto: ${(Number(p?.amountCents) / 100).toFixed(0)} - ${p?.description ?? ""}`;
  if (operation === "ADD_STOCK") return `Stock: +${p?.quantity} de ${p?.productRef ?? p?.productId}`;
  if (operation === "REGISTER_PRODUCT") return `Crear producto "${p?.name ?? "?"}"`;
  return operation;
}

// The act step of a compound, in the owner's words, for the second numbered step.
function actTitle(act: Act): string {
  const op = act.operationType.toUpperCase();
  if (op === "ADD_STOCK") return `Cargar ${act.args.quantity ?? "?"} al stock`;
  return op;
}
function actSub(act: Act): string {
  if (act.operationType.toUpperCase() === "ADD_STOCK") return "entrada de inventario";
  return "";
}

const EXAMPLES = ["vendi 2 medias a 300", "cuanto vendi hoy?", "me entraron 50 pulseras rojas"];

export function Chat() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([
    { role: "bot", text: "Hola. Deci lo que pasa en el negocio y te muestro que voy a hacer antes de confirmar. O preguntame, por ejemplo, 'cuanto vendi hoy'." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  function push(m: Msg) {
    setMsgs((prev) => [...prev, m]);
    setTimeout(() => listRef.current?.scrollTo(0, listRef.current.scrollHeight), 0);
  }
  function updateCard(opToken: string, state: CardState) {
    setMsgs((prev) => prev.map((m) => (m.role === "card" && m.opToken === opToken ? { ...m, state } : m)));
  }
  function markChosen(id: string) {
    setMsgs((prev) => prev.map((m) => (m.role === "disambiguation" && m.id === id ? { ...m, chosen: true } : m)));
  }
  function patchCompound(id: string, patch: Partial<Extract<Msg, { role: "compound" }>>) {
    setMsgs((prev) => prev.map((m) => (m.role === "compound" && m.id === id ? { ...m, ...patch } : m)));
  }

  async function sendMessage(message: string) {
    if (!message || busy) return;
    setInput("");
    push({ role: "user", text: message });
    setBusy(true);
    try {
      const r = await postJson("/api/chat", { message, turnNonce: crypto.randomUUID() });
      if (!r.ok) {
        push({ role: "bot", text: r.error?.message ?? "No pude procesar eso." });
      } else if (r.data.kind === "answer") {
        push({ role: "answer", text: r.data.reply });
      } else if (r.data.kind === "unparsed") {
        push({ role: "bot", text: r.data.reply });
      } else if (r.data.kind === "compound") {
        const s = r.data;
        const reg = s.steps.find((x: { role: string }) => x.role === "register");
        const act = s.steps.find((x: { role: string }) => x.role === "act");
        push({
          role: "compound",
          id: crypto.randomUUID(),
          productName: s.product_name,
          turnNonce: s.turn_nonce,
          step1Token: reg.op_token,
          act: { operationType: act.operation_type, args: act.pending_args, utterance: act.utterance },
          state: "pending",
        });
      } else if (r.data.kind === "disambiguation") {
        const s = r.data;
        push({
          role: "disambiguation",
          id: crypto.randomUUID(),
          operation: s.operation_type,
          idField: s.id_field,
          pendingArgs: s.pending_args ?? {},
          utterance: s.utterance,
          turnNonce: s.turn_nonce,
          candidates: s.candidates,
          chosen: false,
        });
      } else if (r.data.kind === "proposal") {
        const { op_token, auto, operation_type, preview, reversible, consequence } = r.data;
        if (auto) {
          const c = await postJson("/api/ops/confirm", { op_token });
          push({ role: "card", opToken: op_token, operation: operation_type, preview, consequence, needsConfirm: false, reversible: Boolean(reversible), state: c.ok ? "done" : "pending" });
          if (!c.ok) push({ role: "bot", text: `No se pudo confirmar: ${c.error?.message}` });
        } else {
          push({ role: "card", opToken: op_token, operation: operation_type, preview, consequence, needsConfirm: true, reversible: Boolean(reversible), state: "pending" });
        }
      }
    } catch (e) {
      push({ role: "bot", text: `Error de red: ${(e as Error).message}` });
    } finally {
      setBusy(false);
    }
  }

  async function confirm(opToken: string) {
    const c = await postJson("/api/ops/confirm", { op_token: opToken });
    updateCard(opToken, c.ok ? "done" : "pending");
    if (!c.ok) push({ role: "bot", text: `No se pudo confirmar: ${c.error?.message}` });
  }
  async function undo(opToken: string) {
    const c = await postJson("/api/ops/undo", { op_token: opToken });
    if (c.ok) updateCard(opToken, "undone");
    else push({ role: "bot", text: `No se pudo deshacer: ${c.error?.message}` });
  }
  function cancel(opToken: string) {
    updateCard(opToken, "cancelled");
  }

  // Pick a disambiguation candidate (spec 009 AC5): re-stage the op with the server-resolved
  // id on the op's id field. This goes to /api/ops/stage directly, not the parser path, so
  // the id is trusted (it came from a server-minted candidate, never from the model). The
  // staged op comes back as a normal confirm card with its full-consequence line.
  async function chooseCandidate(m: Extract<Msg, { role: "disambiguation" }>, cand: Candidate) {
    if (m.chosen || busy) return;
    markChosen(m.id);
    setBusy(true);
    try {
      const s = await postJson("/api/ops/stage", {
        operationType: m.operation,
        // Merge the picked id ONTO the non-id args the op already resolved (e.g. the new
        // price for UPDATE_PRICE); dropping them would re-stage a no-op and still say Hecho.
        args: pickedStageArgs(m.pendingArgs, m.idField, cand.id),
        utterance: m.utterance,
        turnNonce: m.turnNonce,
      });
      if (!s.ok) {
        push({ role: "bot", text: `No pude preparar eso: ${s.error?.message}` });
        return;
      }
      const d = s.data;
      push({ role: "card", opToken: d.op_token, operation: d.operation_type, preview: d.preview, consequence: d.consequence, needsConfirm: !d.auto, reversible: Boolean(d.reversible), state: "pending" });
    } catch (e) {
      push({ role: "bot", text: `Error de red: ${(e as Error).message}` });
    } finally {
      setBusy(false);
    }
  }

  // Confirm a compound in order via the shared, tested orchestrator. driveCompound creates
  // the product (step 1), then threads the server-minted id into the act and commits it
  // (step 2), each its own commit unit. A step-2 failure is isolated: the product stays
  // created (state "created-only") with a Reintentar for just the act; nothing rolls back.
  async function confirmCompound(m: Extract<Msg, { role: "compound" }>) {
    setBusy(true);
    let createdId: number | null = null;
    try {
      const outcomes = await driveCompound({
        confirmRegister: async () => {
          const c1 = await postJson("/api/ops/confirm", { op_token: m.step1Token });
          if (!c1.ok) throw new Error(c1.error?.message ?? "no pude crear el producto");
          const product = c1.data.result as { id: number } & Record<string, unknown>;
          createdId = product.id;
          return product;
        },
        stageAct: async (productId) => {
          const threaded = threadProductId({ operationType: m.act.operationType, args: m.act.args }, productId);
          const s2 = await postJson("/api/ops/stage", { operationType: threaded.operationType, args: threaded.args, utterance: m.act.utterance, turnNonce: m.turnNonce });
          if (!s2.ok) throw new Error(s2.error?.message ?? "no pude preparar la operacion");
          return { op_token: s2.data.op_token };
        },
        confirmAct: async (opToken) => {
          const c2 = await postJson("/api/ops/confirm", { op_token: opToken });
          if (!c2.ok) throw new Error(c2.error?.message ?? "no pude cargar la operacion");
          return c2.data.result;
        },
      });
      const reg = outcomes.find((o) => o.role === "register");
      const act = outcomes.find((o) => o.role === "act");
      if (!reg?.committed) {
        patchCompound(m.id, { state: "failed", note: `No pude crear "${m.productName}": ${reg?.error ?? "error"}` });
      } else if (!act?.committed) {
        patchCompound(m.id, { state: "created-only", productId: createdId ?? undefined, note: `Cree "${m.productName}", pero no pude cargar la operacion: ${act?.error ?? "error"}` });
      } else {
        patchCompound(m.id, { state: "done" });
      }
    } catch (e) {
      push({ role: "bot", text: `Error de red: ${(e as Error).message}` });
    } finally {
      setBusy(false);
    }
  }

  // Retry only the act after a created-only partial: the product already exists, so this
  // re-threads its id, re-stages, and re-confirms the act alone.
  async function retryAct(m: Extract<Msg, { role: "compound" }>) {
    if (m.productId == null || busy) return;
    setBusy(true);
    try {
      const threaded = threadProductId({ operationType: m.act.operationType, args: m.act.args }, m.productId);
      const s2 = await postJson("/api/ops/stage", { operationType: threaded.operationType, args: threaded.args, utterance: m.act.utterance, turnNonce: m.turnNonce });
      if (!s2.ok) { patchCompound(m.id, { note: `Sigue sin cargar: ${s2.error?.message}` }); return; }
      const c2 = await postJson("/api/ops/confirm", { op_token: s2.data.op_token });
      if (!c2.ok) { patchCompound(m.id, { note: `Sigue sin cargar: ${c2.error?.message}` }); return; }
      patchCompound(m.id, { state: "done", note: undefined });
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 rounded-full bg-indigo-600 px-5 py-3 text-sm font-medium text-white shadow-lg hover:bg-indigo-500"
      >
        Timonel
      </button>
    );
  }

  return (
    <div className="fixed bottom-5 right-5 flex h-[34rem] w-[23rem] flex-col rounded-2xl border border-neutral-200 bg-white shadow-2xl dark:border-neutral-800 dark:bg-neutral-900">
      <header className="flex items-center gap-3 border-b border-neutral-200 px-4 py-3 dark:border-neutral-800">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">B</div>
        <div className="flex-1 leading-tight">
          <div className="text-sm font-semibold">Timonel</div>
          <div className="text-xs text-neutral-400">Beans &amp; Co</div>
        </div>
        <button onClick={() => setOpen(false)} aria-label="Cerrar" className="text-neutral-400 hover:text-neutral-700">×</button>
      </header>

      <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto p-3 text-sm">
        {msgs.length === 1 && (
          <div className="flex flex-wrap gap-2 pb-1">
            {EXAMPLES.map((ex) => (
              <button key={ex} onClick={() => sendMessage(ex)} className="rounded-full border border-neutral-200 px-3 py-1 text-xs text-neutral-600 hover:border-indigo-300 hover:text-indigo-700 dark:border-neutral-700 dark:text-neutral-300">
                {ex}
              </button>
            ))}
          </div>
        )}
        {msgs.map((m, i) => {
          if (m.role === "user")
            return <div key={i} className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-indigo-600 px-3 py-2 text-white">{m.text}</div>;
          if (m.role === "bot")
            return <div key={i} className="max-w-[90%] rounded-2xl rounded-bl-sm bg-neutral-100 px-3 py-2 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200">{m.text}</div>;
          // shape 1: answer, borderless, no button
          if (m.role === "answer")
            return (
              <div key={i} className="max-w-[92%] border-l-2 border-indigo-300 pl-3 text-neutral-800 dark:border-indigo-700 dark:text-neutral-200">
                {m.text}
              </div>
            );
          // compound create card: one card, two numbered steps, one Confirmar
          if (m.role === "compound")
            return (
              <div key={i} className="rounded-xl border border-neutral-200 bg-white p-3 dark:border-neutral-700 dark:bg-neutral-800/50">
                <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-400">Crear y cargar</div>
                <div className="mt-1 font-medium">No tengo &quot;{m.productName}&quot; todavia.</div>
                <div className="text-xs text-neutral-500">Puedo crearla y cargar el stock en un paso.</div>
                <ol className="mt-2 space-y-1.5">
                  <li className="flex gap-2">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[0.7rem] font-semibold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">1</span>
                    <span><span className="font-medium">Crear producto &quot;{m.productName}&quot;</span><span className="block text-xs text-neutral-500">precio pendiente, lo ponemos despues</span></span>
                  </li>
                  <li className="flex gap-2">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[0.7rem] font-semibold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">2</span>
                    <span><span className="font-medium">{actTitle(m.act)}</span>{actSub(m.act) && <span className="block text-xs text-neutral-500">{actSub(m.act)}</span>}</span>
                  </li>
                </ol>
                {m.state === "pending" && (
                  <div className="mt-3 flex gap-2">
                    <button onClick={() => confirmCompound(m)} disabled={busy} className="flex-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50">Confirmar</button>
                    <button onClick={() => patchCompound(m.id, { state: "cancelled" })} className="rounded-lg px-3 py-1.5 text-xs text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200">Ahora no</button>
                  </div>
                )}
                {m.state === "done" && <div className="mt-2 text-xs text-indigo-600 dark:text-indigo-400">Hecho: producto creado y operacion cargada.</div>}
                {m.state === "created-only" && (
                  <div className="mt-2">
                    <div className="text-xs text-amber-600">{m.note}</div>
                    <button onClick={() => retryAct(m)} disabled={busy} className="mt-1.5 rounded-lg bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-500 disabled:opacity-50">Reintentar</button>
                  </div>
                )}
                {m.state === "failed" && <div className="mt-2 text-xs text-amber-600">{m.note}</div>}
                {m.state === "cancelled" && <div className="mt-2 text-xs text-neutral-400">Cancelado</div>}
              </div>
            );
          // shape 3: disambiguation picker (AC5). The owner's reference matched more than
          // one row; each option carries the server-resolved id and re-stages on click.
          if (m.role === "disambiguation")
            return (
              <div key={i} className="rounded-xl border border-amber-200 bg-amber-50 p-3 dark:border-amber-900/60 dark:bg-amber-950/30">
                <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">Cual?</div>
                <div className="mt-1 text-neutral-700 dark:text-neutral-200">Encontre varias. Eleg&iacute; una:</div>
                <div className="mt-2 space-y-1.5">
                  {m.candidates.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => chooseCandidate(m, c)}
                      disabled={m.chosen || busy}
                      className="block w-full rounded-lg border border-amber-200 bg-white px-3 py-1.5 text-left text-xs hover:border-amber-400 disabled:opacity-50 dark:border-amber-900/60 dark:bg-neutral-900"
                    >
                      <span className="font-medium">{c.label}</span>
                      {c.detail && <span className="block text-[0.7rem] text-neutral-500">{c.detail}</span>}
                    </button>
                  ))}
                  <button
                    onClick={() => { markChosen(m.id); push({ role: "bot", text: "Listo, no toco nada." }); }}
                    disabled={m.chosen || busy}
                    className="block w-full px-3 py-1 text-left text-xs text-neutral-500 hover:text-neutral-800 disabled:opacity-50 dark:hover:text-neutral-200"
                  >
                    Ninguna de estas
                  </button>
                </div>
                {m.chosen && <div className="mt-2 text-xs text-neutral-400">Elegido</div>}
              </div>
            );
          // shape 2 (create, neutral/indigo) and shape 3 (cancel/edit, amber, verb-bearing):
          // a destructive or edit op shows its full consequence and a verb-bearing confirm.
          {
            const destructive = DESTRUCTIVE_OPS.has(m.operation.toUpperCase());
            // Full consequence line (server-provided); fall back to a Spanish default for a
            // destructive op if it is ever absent, never a raw opType. Split the first
            // sentence (the identity) from the rest (the effect) for the mockup's two tiers.
            const line = m.consequence || (destructive ? destructiveFallback(m.operation) : summarize(m.operation, m.preview));
            const dot = line.indexOf(". ");
            const identity = dot > 0 ? line.slice(0, dot + 1) : line;
            const effect = dot > 0 ? line.slice(dot + 2) : "";
            return (
              <div key={i} className={`rounded-xl border p-3 ${destructive ? "border-amber-200 bg-amber-50 dark:border-amber-900/60 dark:bg-amber-950/30" : "border-neutral-200 bg-white dark:border-neutral-700 dark:bg-neutral-800/50"}`}>
                {destructive && <div className="text-[0.7rem] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">{actionLabel(m.operation)}</div>}
                <div className={`font-medium ${destructive ? "mt-1" : ""}`}>{identity}</div>
                {effect && <div className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">{effect}</div>}
                {m.state === "pending" && m.needsConfirm && (
                  <div className="mt-2 flex gap-2">
                    <button onClick={() => confirm(m.opToken)} className={`rounded-lg px-3 py-1 text-xs text-white ${destructive ? "bg-amber-600 hover:bg-amber-500" : "bg-indigo-600 hover:bg-indigo-500"}`}>{confirmVerb(m.operation)}</button>
                    <button onClick={() => cancel(m.opToken)} className="rounded-lg px-3 py-1 text-xs text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200">Ahora no</button>
                  </div>
                )}
                {m.state === "done" && (
                  <div className="mt-2 flex items-center gap-2 text-xs text-indigo-600 dark:text-indigo-400">
                    <span>Hecho</span>
                    {m.reversible && (
                      <button onClick={() => undo(m.opToken)} className="rounded bg-amber-100 px-2 py-0.5 text-amber-700 hover:bg-amber-200 dark:bg-amber-950 dark:text-amber-300">Deshacer</button>
                    )}
                  </div>
                )}
                {m.state === "undone" && <div className="mt-2 text-xs text-neutral-400">Deshecho</div>}
                {m.state === "cancelled" && <div className="mt-2 text-xs text-neutral-400">Cancelado</div>}
              </div>
            );
          }
        })}
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); sendMessage(input.trim()); }}
        className="flex gap-2 border-t border-neutral-200 p-3 dark:border-neutral-800"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribi una operacion o una pregunta..."
          className="flex-1 rounded-lg border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 dark:border-neutral-700 dark:bg-neutral-800"
        />
        <button type="submit" disabled={busy} className="rounded-lg bg-indigo-600 px-4 text-sm text-white disabled:opacity-50 hover:bg-indigo-500">
          {busy ? "..." : "Enviar"}
        </button>
      </form>
    </div>
  );
}
