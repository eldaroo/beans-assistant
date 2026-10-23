import { leadComparison } from "@/lib/domains/costing";
import { PageHeader, Card, Money, Empty, Badge } from "../_components/ui";

export const dynamic = "force-dynamic";

export default async function CostosPage() {
  const cmp = await leadComparison();
  return (
    <div>
      <PageHeader title="Costos" subtitle="Costo puesto por pais (tipo lider)" />
      {!cmp ? (
        <Empty>Todavia no hay un producto con receta (BOM) para costear.</Empty>
      ) : (
        <div>
          <div className="mb-4 text-sm text-neutral-600 dark:text-neutral-300">
            {cmp.productName}
            {cmp.lowestCompleteCountry ? (
              <> · mas barato de producir: <Badge tone="ok">{cmp.lowestCompleteCountry}</Badge></>
            ) : (
              <> · <Badge tone="warn">ningun pais con costo completo aun</Badge></>
            )}
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {cmp.margins.map((m) => (
              <Card key={m.country}>
                <div className="flex items-center justify-between">
                  <div className="font-medium text-neutral-900 dark:text-neutral-100">{m.country}</div>
                  <Badge tone={m.landed.isComplete ? "ok" : "warn"}>{m.landed.status}</Badge>
                </div>
                <div className="mt-3 space-y-1 text-sm">
                  {m.landed.components.map((c) => (
                    <div key={c.key} className="flex justify-between">
                      <span className="text-neutral-500">{c.label}</span>
                      <span><Money cents={c.cents} /></span>
                    </div>
                  ))}
                  <div className="mt-2 flex justify-between border-t border-neutral-200 pt-2 font-medium dark:border-neutral-800">
                    <span>Costo puesto</span>
                    <span><Money cents={m.landed.isComplete ? m.landed.totalCents : null} /></span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Margen</span>
                    <span>{m.marginCents === null ? <span className="text-neutral-400">{m.pendingReason}</span> : <Money cents={m.marginCents} />}</span>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
