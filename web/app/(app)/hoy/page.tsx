import { dashboardSnapshot } from "@/lib/domains/analytics";
import { listProducts } from "@/lib/domains/products";
import { overdueArrivals } from "@/lib/domains/production";
import { overdueCheckins, countActive } from "@/lib/domains/suppliers";
import { pendingCustoms } from "@/lib/domains/logistics";
import { PageHeader, Stat, Card, Badge, Empty } from "../_components/ui";

export const dynamic = "force-dynamic";

function usd(n: number | null): string {
  if (n === null) return "pendiente";
  return n.toLocaleString("es-AR", { style: "currency", currency: "USD" });
}

export default async function Hoy() {
  const [snap, products, arrivals, checkins, suppliers, customs] = await Promise.all([
    dashboardSnapshot(),
    listProducts(),
    overdueArrivals(),
    overdueCheckins(),
    countActive(),
    pendingCustoms(),
  ]);
  const attention = arrivals.length + checkins.length + customs.length;

  return (
    <div>
      <PageHeader title="Hoy" subtitle="Resumen del negocio" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Ingresos (pagados)" value={usd(snap.revenueUsd)} />
        <Stat label="Ganancia" value={usd(snap.profitUsd)} />
        <Stat label="Productos activos" value={products.length} />
        <Stat label="Proveedores activos" value={suppliers} />
      </div>

      <h2 className="mt-8 mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-300">
        Atencion {attention > 0 ? <Badge tone="warn">{attention}</Badge> : <Badge tone="ok">al dia</Badge>}
      </h2>
      {attention === 0 ? (
        <Empty>No hay senales de atencion pendientes.</Empty>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <div className="mb-2 text-xs uppercase tracking-wide text-neutral-500">Llegadas atrasadas</div>
            {arrivals.length === 0 ? (
              <div className="text-sm text-neutral-400">ninguna</div>
            ) : (
              arrivals.map((a, i) => (
                <div key={i} className="text-sm text-neutral-700 dark:text-neutral-300">
                  {a.country} · esperada {a.expectedNextAt}
                </div>
              ))
            )}
          </Card>
          <Card>
            <div className="mb-2 text-xs uppercase tracking-wide text-neutral-500">Check-ins vencidos</div>
            {checkins.length === 0 ? (
              <div className="text-sm text-neutral-400">ninguno</div>
            ) : (
              checkins.map((s) => (
                <div key={s.id} className="text-sm text-neutral-700 dark:text-neutral-300">
                  {s.name} · {s.daysSinceCheckin} dias
                </div>
              ))
            )}
          </Card>
          <Card>
            <div className="mb-2 text-xs uppercase tracking-wide text-neutral-500">Aduana pendiente</div>
            {customs.length === 0 ? (
              <div className="text-sm text-neutral-400">ninguna</div>
            ) : (
              customs.map((l, i) => (
                <div key={i} className="text-sm text-neutral-700 dark:text-neutral-300">{l.country}</div>
              ))
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
