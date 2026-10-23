import { currentStock } from "@/lib/domains/stock";
import { PageHeader, Table, Td, Empty, Badge } from "../_components/ui";

export const dynamic = "force-dynamic";

export default async function StockPage() {
  const rows = await currentStock();
  return (
    <div>
      <PageHeader title="Stock" subtitle="Existencias por producto activo" />
      {rows.length === 0 ? (
        <Empty>No hay productos con stock registrado.</Empty>
      ) : (
        <Table head={["SKU", "Producto", "En mano"]}>
          {rows.map((r) => (
            <tr key={r.product_id}>
              <Td className="font-mono text-xs">{r.sku}</Td>
              <Td>{r.name}</Td>
              <Td>
                {r.stock_qty <= 0 ? <Badge tone="warn">{r.stock_qty}</Badge> : r.stock_qty}
              </Td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
