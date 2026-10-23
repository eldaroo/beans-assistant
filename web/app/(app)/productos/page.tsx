import { listProducts } from "@/lib/domains/products";
import { PageHeader, Table, Td, Money, Empty, Badge } from "../_components/ui";

export const dynamic = "force-dynamic";

export default async function ProductosPage() {
  const rows = await listProducts({ includeInactive: true });
  return (
    <div>
      <PageHeader title="Productos" subtitle="Catalogo" />
      {rows.length === 0 ? (
        <Empty>Todavia no hay productos.</Empty>
      ) : (
        <Table head={["SKU", "Nombre", "Costo", "Precio", "Estado"]}>
          {rows.map((p) => (
            <tr key={p.id}>
              <Td className="font-mono text-xs">{p.sku}</Td>
              <Td>{p.name}</Td>
              <Td><Money cents={p.unitCostCents} /></Td>
              <Td><Money cents={p.unitPriceCents} /></Td>
              <Td>{p.isActive ? <Badge tone="ok">activo</Badge> : <Badge>inactivo</Badge>}</Td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
