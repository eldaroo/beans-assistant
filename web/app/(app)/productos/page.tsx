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
        <Table head={["Nombre", "Costo", "Precio", "Estado"]}>
          {rows.map((p) => (
            <tr key={p.id}>
              <Td>{p.name}</Td>
              {/* A name-only minted product carries unit cost 0 with no price yet; show the
                  cost as "pendiente", not an authoritative US$ 0,00, so a placeholder is
                  never read as a real zero cost (spec 009 Edut honesty review). */}
              <Td>{p.unitCostCents === 0 && p.unitPriceCents === null ? <span className="text-neutral-400">pendiente</span> : <Money cents={p.unitCostCents} />}</Td>
              <Td><Money cents={p.unitPriceCents} /></Td>
              <Td>{p.isActive ? <Badge tone="ok">activo</Badge> : <Badge>inactivo</Badge>}</Td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
