import { leadLanes } from "@/lib/domains/logistics";
import { PageHeader, Table, Td, Money, Empty, Badge } from "../_components/ui";

export const dynamic = "force-dynamic";

export default async function LogisticaPage() {
  const lanes = await leadLanes();
  return (
    <div>
      <PageHeader title="Logistica" subtitle="Envio + aduana por pais (tipo lider)" />
      {!lanes ? (
        <Empty>Todavia no hay un producto costeable para ver sus rutas.</Empty>
      ) : (
        <Table head={["Pais", "Envio", "Aduana", "Total", "Estado"]}>
          {lanes.map((l) => (
            <tr key={l.country}>
              <Td>{l.country}</Td>
              <Td><Money cents={l.shippingCents} /></Td>
              <Td><Money cents={l.customsCents} /></Td>
              <Td><Money cents={l.isComplete ? l.totalCents : null} /></Td>
              <Td>
                {l.isComplete ? (
                  <Badge tone="ok">completa</Badge>
                ) : (
                  <Badge tone="warn">falta {l.pendingLabels.join(", ")}</Badge>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
