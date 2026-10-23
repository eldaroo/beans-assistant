import { currentWeek, perCountry } from "@/lib/domains/production";
import { PageHeader, Stat, Table, Td, Empty, Badge } from "../_components/ui";

export const dynamic = "force-dynamic";

export default async function ProduccionPage() {
  const [rollup, byCountry] = await Promise.all([currentWeek(), perCountry()]);
  return (
    <div>
      <PageHeader title="Produccion" subtitle="Unidades por semana vs objetivo" />
      {rollup ? (
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-3">
          <Stat label="Semana" value={rollup.periodWeek} />
          <Stat label="Producidas" value={rollup.unitsProduced} />
          <Stat label="Objetivo" value={rollup.unitsTarget ?? "-"} hint={rollup.pctOfTarget !== null ? `${rollup.pctOfTarget}% del objetivo` : undefined} />
        </div>
      ) : null}
      {byCountry.length === 0 ? (
        <Empty>Todavia no hay produccion registrada.</Empty>
      ) : (
        <Table head={["Pais", "Semana", "Producidas", "Objetivo", "%", "Proxima"]}>
          {byCountry.map((s, i) => (
            <tr key={i}>
              <Td>{s.country}</Td>
              <Td className="font-mono text-xs">{s.periodWeek}</Td>
              <Td>{s.unitsProduced}</Td>
              <Td>{s.unitsTarget ?? "-"}</Td>
              <Td>{s.pctOfTarget !== null ? `${s.pctOfTarget}%` : "-"}</Td>
              <Td>{s.isOverdue ? <Badge tone="warn">atrasada {s.expectedNextAt}</Badge> : (s.expectedNextAt ?? "-")}</Td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
