"use client";
import { useRef, useState } from "react";

type Msg =
  | { role: "user"; text: string }
  | { role: "bot"; text: string }
  | { role: "card"; opToken: string; operation: string; preview: unknown; needsConfirm: boolean; state: "pending" | "done" | "undone" | "cancelled" };

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
  return operation;
}

export function Chat() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([
    { role: "bot", text: "Hola. Deci algo como 'vendi 2 medias a 300', 'gaste 500 en envio' o preguntame un escenario de costos." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  function push(m: Msg) {
    setMsgs((prev) => [...prev, m]);
    setTimeout(() => listRef.current?.scrollTo(0, listRef.current.scrollHeight), 0);
  }
  function updateCard(opToken: string, state: "pending" | "done" | "undone" | "cancelled") {
    setMsgs((prev) => prev.map((m) => (m.role === "card" && m.opToken === opToken ? { ...m, state } : m)));
  }

  async function send() {
    const message = input.trim();
    if (!message || busy) return;
    setInput("");
    push({ role: "user", text: message });
    setBusy(true);
    try {
      const r = await postJson("/api/chat", { message, turnNonce: crypto.randomUUID() });
      if (!r.ok) {
        push({ role: "bot", text: `Error: ${r.error?.message ?? "fallo"}` });
      } else if (r.data.kind === "answer" || r.data.kind === "unparsed") {
        push({ role: "bot", text: r.data.reply });
      } else if (r.data.kind === "proposal") {
        const { op_token, auto, operation_type, preview } = r.data;
        if (auto) {
          const c = await postJson("/api/ops/confirm", { op_token });
          push({ role: "card", opToken: op_token, operation: operation_type, preview, needsConfirm: false, state: c.ok ? "done" : "pending" });
          if (!c.ok) push({ role: "bot", text: `No se pudo confirmar: ${c.error?.message}` });
        } else {
          push({ role: "card", opToken: op_token, operation: operation_type, preview, needsConfirm: true, state: "pending" });
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

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 rounded-full bg-neutral-900 px-5 py-3 text-sm font-medium text-white shadow-lg hover:bg-neutral-700 dark:bg-white dark:text-neutral-900"
      >
        Timonel
      </button>
    );
  }

  return (
    <div className="fixed bottom-5 right-5 flex h-[32rem] w-[22rem] flex-col rounded-xl border border-neutral-200 bg-white shadow-2xl dark:border-neutral-800 dark:bg-neutral-900">
      <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-3 dark:border-neutral-800">
        <span className="text-sm font-semibold">Timonel</span>
        <button onClick={() => setOpen(false)} className="text-neutral-400 hover:text-neutral-700">×</button>
      </div>
      <div ref={listRef} className="flex-1 space-y-2 overflow-y-auto p-3 text-sm">
        {msgs.map((m, i) => {
          if (m.role === "user") return <div key={i} className="ml-auto max-w-[85%] rounded-lg bg-neutral-900 px-3 py-2 text-white dark:bg-white dark:text-neutral-900">{m.text}</div>;
          if (m.role === "bot") return <div key={i} className="max-w-[90%] rounded-lg bg-neutral-100 px-3 py-2 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200">{m.text}</div>;
          // card
          return (
            <div key={i} className="rounded-lg border border-neutral-300 p-3 dark:border-neutral-700">
              <div className="font-medium">{summarize(m.operation, m.preview)}</div>
              {m.state === "pending" && m.needsConfirm && (
                <div className="mt-2 flex gap-2">
                  <button onClick={() => confirm(m.opToken)} className="rounded bg-emerald-600 px-3 py-1 text-xs text-white hover:bg-emerald-500">Confirmar</button>
                  <button onClick={() => cancel(m.opToken)} className="rounded bg-neutral-200 px-3 py-1 text-xs text-neutral-700 hover:bg-neutral-300 dark:bg-neutral-700 dark:text-neutral-200">Cancelar</button>
                </div>
              )}
              {m.state === "done" && (
                <div className="mt-2 flex items-center gap-2 text-xs text-emerald-600">
                  <span>Hecho</span>
                  <button onClick={() => undo(m.opToken)} className="rounded bg-amber-100 px-2 py-0.5 text-amber-700 hover:bg-amber-200 dark:bg-amber-950 dark:text-amber-300">Deshacer</button>
                </div>
              )}
              {m.state === "undone" && <div className="mt-2 text-xs text-neutral-400">Deshecho</div>}
              {m.state === "cancelled" && <div className="mt-2 text-xs text-neutral-400">Cancelado</div>}
            </div>
          );
        })}
      </div>
      <form
        onSubmit={(e) => { e.preventDefault(); send(); }}
        className="flex gap-2 border-t border-neutral-200 p-3 dark:border-neutral-800"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribi una operacion..."
          className="flex-1 rounded-md border border-neutral-300 px-3 py-2 text-sm outline-none focus:border-neutral-500 dark:border-neutral-700 dark:bg-neutral-800"
        />
        <button type="submit" disabled={busy} className="rounded-md bg-neutral-900 px-4 text-sm text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900">
          {busy ? "..." : "Enviar"}
        </button>
      </form>
    </div>
  );
}
