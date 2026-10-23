import { listSales } from "@/lib/domains/sales";
import { PageHeader, Table, Td, Money, Empty, Badge } from "../_components/ui";

export const dynamic = "force-dynamic";

function tone(status: string): "ok" | "warn" | "neutral" {
  if (status === "PAID") return "ok";
  if (status === "CANCELLED") return "warn";
  return "neutral";
}

export default async function VentasPage() {
  const rows = await listSales({ limit: 100 });
  return (
    <div>
      <PageHeader title="Ventas" subtitle="Ultimas ventas" />
      {rows.length === 0 ? (
        <Empty>Todavia no hay ventas.</Empty>
      ) : (
        <Table head={["Numero", "Estado", "Total", "Cliente", "Fecha"]}>
          {rows.map((s) => (
            <tr key={s.id}>
              <Td className="font-mono text-xs">{s.saleNumber}</Td>
              <Td><Badge tone={tone(s.status)}>{s.status}</Badge></Td>
              <Td><Money cents={s.totalAmountCents} /></Td>
              <Td>{s.customerName ?? "-"}</Td>
              <Td className="text-xs text-neutral-500">{new Date(s.createdAt).toLocaleString("es-AR")}</Td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
