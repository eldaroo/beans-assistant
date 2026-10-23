import { revenuePaidCents, profitUsd, salesSummary } from "@/lib/domains/analytics";
import { expensesTotalCents } from "@/lib/domains/expenses";
import { PageHeader, Stat, Table, Td, Empty } from "../_components/ui";
import { centsToUsd } from "@/lib/money";

export const dynamic = "force-dynamic";

function usd(n: number | null): string {
  if (n === null) return "-";
  return n.toLocaleString("es-AR", { style: "currency", currency: "USD" });
}

export default async function ResultadoPage() {
  const [revCents, expCents, profit, daily] = await Promise.all([
    revenuePaidCents(),
    expensesTotalCents(),
    profitUsd(),
    salesSummary(30),
  ]);
  return (
    <div>
      <PageHeader title="Resultado" subtitle="Ingresos, egresos y ganancia" />
      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="Ingresos (pagados)" value={usd(centsToUsd(revCents))} />
        <Stat label="Egresos (netos)" value={usd(centsToUsd(expCents))} />
        <Stat label="Ganancia" value={usd(profit)} />
      </div>
      <h2 className="mb-3 text-sm font-semibold text-neutral-700 dark:text-neutral-300">Ventas por dia</h2>
      {daily.length === 0 ? (
        <Empty>Todavia no hay ventas pagadas.</Empty>
      ) : (
        <Table head={["Dia", "Ventas", "Ingreso"]}>
          {daily.map((d) => (
            <tr key={d.day}>
              <Td>{d.day}</Td>
              <Td>{d.paid_sales_count}</Td>
              <Td>{usd(d.paid_revenue_usd)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
