import { directory } from "@/lib/domains/suppliers";
import { PageHeader, Table, Td, Empty, Badge } from "../_components/ui";

export const dynamic = "force-dynamic";

export default async function ProveedoresPage() {
  const rows = await directory();
  return (
    <div>
      <PageHeader title="Proveedores" subtitle="Directorio y estado de check-in" />
      {rows.length === 0 ? (
        <Empty>Todavia no hay proveedores.</Empty>
      ) : (
        <Table head={["Nombre", "Pais", "Contacto", "Ultimo check-in", "Estado"]}>
          {rows.map((s) => (
            <tr key={s.id}>
              <Td>{s.name}</Td>
              <Td>{s.country ?? "-"}</Td>
              <Td>{s.contact ?? "-"}</Td>
              <Td className="text-xs text-neutral-500">
                {s.lastCheckinAt ? `${s.daysSinceCheckin} dias` : "sin check-in"}
              </Td>
              <Td>{s.isOverdue ? <Badge tone="warn">vencido</Badge> : <Badge tone="ok">al dia</Badge>}</Td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
