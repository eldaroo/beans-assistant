// Command-center read aggregations for the internal-ops read surface (spec 010 M2, s-02).
// These back the MCP read_module and business_status tools: moduleSnapshot(id) returns one
// module's current headline plus anything in it that needs attention, and attentionSnapshot()
// returns the one prioritized "what needs attention today" aggregation the Hoy command-center
// home shows. Every number is derived from the same domain reads the pages use, never from the
// model (D-036): the box reads live data, it does not invent it.
//
// business_status is byte-equal to the Hoy attention aggregation BY CONSTRUCTION: the Hoy route
// (GET /api/hoy) and the internal business_status endpoint both call attentionSnapshot(), so a
// single source produces the list and the two cannot drift (T-010). The MCP business_status
// description tells the model this is "the same list the command-center home shows; never
// invent items" — this is the function that makes that true.
import { revenuePaidCents, profitUsd } from "@/lib/domains/analytics";
import { expensesTotalCents } from "@/lib/domains/expenses";
import { currentStock } from "@/lib/domains/stock";
import { listProducts } from "@/lib/domains/products";
import { listSales } from "@/lib/domains/sales";
import { leadComparison } from "@/lib/domains/costing";
import { currentWeek, overdueArrivals } from "@/lib/domains/production";
import { leadLanes, pendingCustoms } from "@/lib/domains/logistics";
import { countActive, overdueCheckins } from "@/lib/domains/suppliers";
import { centsToUsd } from "@/lib/money";
import type { ProductionStatus } from "@/lib/domains/production";
import type { LogisticsLane } from "@/lib/domains/logistics";
import type { SupplierStatus } from "@/lib/domains/suppliers";

// The eight command-center modules, by their registry ids. Kept in lockstep with the MCP
// read_module enum (deploy/beans-mcp.mjs MODULE_IDS); a module id outside this set is a tool
// error (invalid_module), never a silent wrong read.
export const MODULE_IDS = [
  "caja", "productos", "stock", "ventas", "costos", "produccion", "logistica", "proveedores",
] as const;
export type ModuleId = (typeof MODULE_IDS)[number];

export function isModuleId(x: unknown): x is ModuleId {
  return typeof x === "string" && (MODULE_IDS as readonly string[]).includes(x);
}

export interface AttentionSnapshot {
  overdue_arrivals: ProductionStatus[];
  overdue_checkins: SupplierStatus[];
  pending_customs: LogisticsLane[];
}

// The one prioritized "what needs attention today" aggregation across the whole business.
// Shared by GET /api/hoy and the internal business_status endpoint so the two are byte-equal.
export async function attentionSnapshot(): Promise<AttentionSnapshot> {
  const [arrivals, checkins, customs] = await Promise.all([
    overdueArrivals(),
    overdueCheckins(),
    pendingCustoms(),
  ]);
  return { overdue_arrivals: arrivals, overdue_checkins: checkins, pending_customs: customs };
}

export interface ModuleSnapshot {
  module: ModuleId;
  title: string;
  headline: Record<string, unknown>;
  attention: unknown[];
}

// One command-center module's current headline plus anything in it that needs attention,
// derived from the same domain reads the matching page renders. The switch is total over
// MODULE_IDS so TypeScript proves every registered module has a snapshot.
export async function moduleSnapshot(module: ModuleId): Promise<ModuleSnapshot> {
  switch (module) {
    case "caja": {
      const [revCents, expCents, profit] = await Promise.all([
        revenuePaidCents(), expensesTotalCents(), profitUsd(),
      ]);
      return {
        module, title: "Resultado",
        headline: {
          revenue_usd: centsToUsd(revCents),
          expenses_usd: centsToUsd(expCents),
          profit_usd: profit,
        },
        attention: [],
      };
    }
    case "productos": {
      const all = await listProducts({ includeInactive: true });
      const active = all.filter((p) => p.isActive);
      return {
        module, title: "Productos",
        headline: { active_count: active.length, total_count: all.length },
        attention: [],
      };
    }
    case "stock": {
      const rows = await currentStock();
      const out = rows
        .filter((r) => r.stock_qty <= 0)
        .map((r) => ({ name: r.name, sku: r.sku, stock_qty: r.stock_qty }));
      return {
        module, title: "Stock",
        headline: { products_tracked: rows.length, out_of_stock: out.length },
        attention: out,
      };
    }
    case "ventas": {
      // The most recent window only, never a lifetime total: report the count shown AND the
      // window size so the model cannot read a capped number as the total (Amelia, council M2).
      // Day-by-day totals are the read_sales_summary tool's job, not this snapshot's.
      const windowSize = 30;
      const rows = await listSales({ limit: windowSize });
      return {
        module, title: "Ventas",
        headline: { recent_sales_count: rows.length, window_most_recent: windowSize },
        attention: [],
      };
    }
    case "costos": {
      const cmp = await leadComparison();
      const incomplete = cmp
        ? cmp.margins
            .filter((m) => !m.landed.isComplete)
            .map((m) => ({ country: m.landed.country, pending: m.landed.pendingLabels }))
        : [];
      return {
        module, title: "Costos",
        headline: {
          product: cmp?.productName ?? null,
          cheapest_complete_country: cmp?.lowestCompleteCountry ?? null,
          has_complete_costing: Boolean(cmp?.lowestCompleteCountry),
        },
        attention: incomplete,
      };
    }
    case "produccion": {
      const [week, arrivals] = await Promise.all([currentWeek(), overdueArrivals()]);
      return {
        module, title: "Produccion",
        headline: week
          ? {
              week: week.periodWeek,
              produced: week.unitsProduced,
              target: week.unitsTarget,
              pct_of_target: week.pctOfTarget,
            }
          : { week: null },
        attention: arrivals.map((a) => ({ country: a.country, expected_next_at: a.expectedNextAt })),
      };
    }
    case "logistica": {
      const [lanes, customs] = await Promise.all([leadLanes(), pendingCustoms()]);
      const list = lanes ?? [];
      return {
        module, title: "Logistica",
        headline: {
          lanes_total: list.length,
          lanes_complete: list.filter((l) => l.isComplete).length,
        },
        attention: customs.map((c) => ({ country: c.country, pending: c.pendingLabels })),
      };
    }
    case "proveedores": {
      const [active, overdue] = await Promise.all([countActive(), overdueCheckins()]);
      return {
        module, title: "Proveedores",
        headline: { active_count: active },
        attention: overdue.map((s) => ({ name: s.name, days_since_checkin: s.daysSinceCheckin })),
      };
    }
  }
}
