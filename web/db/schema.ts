// Beans & Co single-business schema (spec 008, M1).
//
// This is the flat, single-tenant port of the per-tenant Postgres schema the
// FastAPI app created at runtime (database_pg.py + postgres/migrations/*). The
// old app isolated tenants with one Postgres SCHEMA per phone number
// (SET search_path TO tenant_<phone>), so the business tables never carried a
// tenant column. Flattening the single live business (+54955885565) therefore
// drops nothing from a row: it only drops the schema-per-tenant indirection and
// the public.tenants / public.app_users plumbing (auth is now Google OAuth +
// BEANS_ALLOWED_EMAILS).
//
// Money is always integer *_cents. A nullable *_cents means the component is
// pending (unknown), never a real zero. Two-phase writes (pending_ops) and the
// append-only audit_log are preserved from spec 007.

import { sql } from "drizzle-orm";
import {
  pgTable,
  bigserial,
  bigint,
  varchar,
  text,
  integer,
  boolean,
  timestamp,
  date,
  numeric,
  check,
  uniqueIndex,
} from "drizzle-orm/pg-core";

// ---------------------------------------------------------------------------
// Core domains: products, sales, stock, expenses
// ---------------------------------------------------------------------------

export const products = pgTable(
  "products",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    sku: varchar("sku", { length: 100 }).notNull().unique(),
    name: varchar("name", { length: 255 }).notNull(),
    description: text("description"),
    unitCostCents: integer("unit_cost_cents").notNull().default(0),
    unitPriceCents: integer("unit_price_cents"),
    isActive: boolean("is_active").notNull().default(true),
    createdAt: timestamp("created_at").notNull().defaultNow(),
  },
  (t) => [
    check("check_unit_cost_positive", sql`${t.unitCostCents} >= 0`),
    check(
      "check_unit_price_positive",
      sql`${t.unitPriceCents} IS NULL OR ${t.unitPriceCents} >= 0`,
    ),
  ],
);

export const sales = pgTable(
  "sales",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    saleNumber: varchar("sale_number", { length: 50 }).notNull().unique(),
    customerName: varchar("customer_name", { length: 255 }),
    status: varchar("status", { length: 20 }).notNull(),
    currency: varchar("currency", { length: 3 }).notNull().default("USD"),
    totalAmountCents: integer("total_amount_cents").notNull(),
    createdAt: timestamp("created_at").notNull().defaultNow(),
    paidAt: timestamp("paid_at"),
  },
  (t) => [
    check("sales_status_check", sql`${t.status} IN ('PAID','PENDING','CANCELLED')`),
    check("sales_total_nonneg", sql`${t.totalAmountCents} >= 0`),
  ],
);

export const saleItems = pgTable(
  "sale_items",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    saleId: bigint("sale_id", { mode: "number" })
      .notNull()
      .references(() => sales.id, { onDelete: "cascade" }),
    productId: bigint("product_id", { mode: "number" })
      .notNull()
      .references(() => products.id),
    quantity: integer("quantity").notNull(),
    unitPriceCents: integer("unit_price_cents").notNull(),
    lineTotalCents: integer("line_total_cents").notNull(),
  },
  (t) => [check("sale_items_qty_positive", sql`${t.quantity} > 0`)],
);

export const stockMovements = pgTable(
  "stock_movements",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    productId: bigint("product_id", { mode: "number" })
      .notNull()
      .references(() => products.id),
    movementType: varchar("movement_type", { length: 20 }).notNull(),
    quantity: integer("quantity").notNull(),
    reason: text("reason"),
    reference: varchar("reference", { length: 100 }),
    occurredAt: timestamp("occurred_at").notNull().defaultNow(),
    createdAt: timestamp("created_at").notNull().defaultNow(),
  },
  (t) => [
    check(
      "stock_movement_type_check",
      sql`${t.movementType} IN ('IN','OUT','ADJUSTMENT')`,
    ),
    check("stock_qty_nonzero", sql`${t.quantity} <> 0`),
  ],
);

export const expenses = pgTable(
  "expenses",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    expenseDate: date("expense_date").notNull().default(sql`CURRENT_DATE`),
    category: varchar("category", { length: 50 }).notNull(),
    description: text("description"),
    amountCents: integer("amount_cents").notNull(),
    currency: varchar("currency", { length: 3 }).notNull().default("USD"),
    createdAt: timestamp("created_at").notNull().defaultNow(),
  },
  (t) => [check("expenses_amount_nonneg", sql`${t.amountCents} >= 0`)],
);

// ---------------------------------------------------------------------------
// Suppliers + costing (BOM, labor, packaging, shipping, customs, indirect)
// ---------------------------------------------------------------------------

export const suppliers = pgTable("suppliers", {
  id: bigserial("id", { mode: "number" }).primaryKey(),
  name: varchar("name", { length: 255 }).notNull(),
  country: varchar("country", { length: 64 }),
  contact: varchar("contact", { length: 255 }),
  isActive: boolean("is_active").notNull().default(true),
  lastCheckinAt: timestamp("last_checkin_at"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
});

export const costInputs = pgTable("cost_inputs", {
  id: bigserial("id", { mode: "number" }).primaryKey(),
  name: varchar("name", { length: 255 }).notNull(),
  category: varchar("category", { length: 64 }),
  unit: varchar("unit", { length: 32 }),
  createdAt: timestamp("created_at").notNull().defaultNow(),
});

export const inputPurchases = pgTable(
  "input_purchases",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    costInputId: bigint("cost_input_id", { mode: "number" })
      .notNull()
      .references(() => costInputs.id),
    supplierId: bigint("supplier_id", { mode: "number" }).references(
      () => suppliers.id,
    ),
    originalCurrency: varchar("original_currency", { length: 3 })
      .notNull()
      .default("USD"),
    originalAmountCents: integer("original_amount_cents").notNull(),
    fxRate: numeric("fx_rate", { precision: 18, scale: 8 }).notNull().default("1"),
    usdAmountCents: integer("usd_amount_cents").notNull(),
    quantity: numeric("quantity", { precision: 18, scale: 4 })
      .notNull()
      .default("1"),
    purchasedAt: date("purchased_at").notNull().default(sql`CURRENT_DATE`),
    createdAt: timestamp("created_at").notNull().defaultNow(),
  },
  (t) => [
    check("input_purchases_orig_nonneg", sql`${t.originalAmountCents} >= 0`),
    check("input_purchases_fx_positive", sql`${t.fxRate} > 0`),
    check("input_purchases_usd_nonneg", sql`${t.usdAmountCents} >= 0`),
    check("input_purchases_qty_positive", sql`${t.quantity} > 0`),
  ],
);

export const bomLines = pgTable(
  "bom_lines",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    productId: bigint("product_id", { mode: "number" })
      .notNull()
      .references(() => products.id),
    costInputId: bigint("cost_input_id", { mode: "number" })
      .notNull()
      .references(() => costInputs.id),
    country: varchar("country", { length: 64 }).notNull(),
    quantity: numeric("quantity", { precision: 18, scale: 4 })
      .notNull()
      .default("1"),
    createdAt: timestamp("created_at").notNull().defaultNow(),
  },
  (t) => [check("bom_lines_qty_positive", sql`${t.quantity} > 0`)],
);

export const laborCosts = pgTable(
  "labor_costs",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    productId: bigint("product_id", { mode: "number" })
      .notNull()
      .references(() => products.id),
    country: varchar("country", { length: 64 }).notNull(),
    batchPaymentCents: integer("batch_payment_cents").notNull(),
    unitsCompleted: integer("units_completed").notNull(),
    recordedAt: date("recorded_at").notNull().default(sql`CURRENT_DATE`),
    createdAt: timestamp("created_at").notNull().defaultNow(),
  },
  (t) => [
    check("labor_payment_nonneg", sql`${t.batchPaymentCents} >= 0`),
    check("labor_units_nonneg", sql`${t.unitsCompleted} >= 0`),
  ],
);

export const packagingCosts = pgTable(
  "packaging_costs",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    productId: bigint("product_id", { mode: "number" })
      .notNull()
      .references(() => products.id),
    country: varchar("country", { length: 64 }).notNull(),
    usdAmountCents: integer("usd_amount_cents").notNull(),
    createdAt: timestamp("created_at").notNull().defaultNow(),
  },
  (t) => [check("packaging_usd_nonneg", sql`${t.usdAmountCents} >= 0`)],
);

export const shippingLanes = pgTable(
  "shipping_lanes",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    productId: bigint("product_id", { mode: "number" })
      .notNull()
      .references(() => products.id),
    country: varchar("country", { length: 64 }).notNull(),
    usdAmountCents: integer("usd_amount_cents"),
    note: text("note"),
    createdAt: timestamp("created_at").notNull().defaultNow(),
  },
  (t) => [
    check(
      "shipping_usd_nonneg",
      sql`${t.usdAmountCents} IS NULL OR ${t.usdAmountCents} >= 0`,
    ),
  ],
);

export const customsDuties = pgTable(
  "customs_duties",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    productId: bigint("product_id", { mode: "number" })
      .notNull()
      .references(() => products.id),
    country: varchar("country", { length: 64 }).notNull(),
    usdAmountCents: integer("usd_amount_cents"),
    note: text("note"),
    createdAt: timestamp("created_at").notNull().defaultNow(),
  },
  (t) => [
    check(
      "customs_usd_nonneg",
      sql`${t.usdAmountCents} IS NULL OR ${t.usdAmountCents} >= 0`,
    ),
  ],
);

export const indirectCosts = pgTable(
  "indirect_costs",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    country: varchar("country", { length: 64 }).notNull(),
    periodMonth: varchar("period_month", { length: 7 }).notNull(),
    poolCents: integer("pool_cents").notNull(),
    unitsProduced: integer("units_produced"),
    createdAt: timestamp("created_at").notNull().defaultNow(),
  },
  (t) => [check("indirect_pool_nonneg", sql`${t.poolCents} >= 0`)],
);

export const landedCostSnapshots = pgTable(
  "landed_cost_snapshots",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    productId: bigint("product_id", { mode: "number" })
      .notNull()
      .references(() => products.id),
    country: varchar("country", { length: 64 }).notNull(),
    materialsCents: integer("materials_cents"),
    laborCents: integer("labor_cents"),
    packagingCents: integer("packaging_cents"),
    shippingCents: integer("shipping_cents"),
    customsCents: integer("customs_cents"),
    indirectCents: integer("indirect_cents"),
    totalCents: integer("total_cents").notNull().default(0),
    status: varchar("status", { length: 16 }).notNull().default("parcial"),
    pendingComponents: text("pending_components"),
    computedAt: timestamp("computed_at").notNull().defaultNow(),
    createdAt: timestamp("created_at").notNull().defaultNow(),
  },
  (t) => [
    check("landed_total_nonneg", sql`${t.totalCents} >= 0`),
    check("landed_status_check", sql`${t.status} IN ('completo','parcial')`),
  ],
);

// ---------------------------------------------------------------------------
// Production
// ---------------------------------------------------------------------------

export const productionRecords = pgTable(
  "production_records",
  {
    id: bigserial("id", { mode: "number" }).primaryKey(),
    productId: bigint("product_id", { mode: "number" }).references(
      () => products.id,
    ),
    country: varchar("country", { length: 64 }).notNull(),
    periodWeek: varchar("period_week", { length: 8 }).notNull(),
    unitsProduced: integer("units_produced").notNull().default(0),
    unitsTarget: integer("units_target"),
    expectedNextAt: date("expected_next_at"),
    recordedAt: date("recorded_at").notNull().default(sql`CURRENT_DATE`),
    createdAt: timestamp("created_at").notNull().defaultNow(),
  },
  (t) => [
    check("production_produced_nonneg", sql`${t.unitsProduced} >= 0`),
    check(
      "production_target_nonneg",
      sql`${t.unitsTarget} IS NULL OR ${t.unitsTarget} >= 0`,
    ),
  ],
);

// ---------------------------------------------------------------------------
// Two-phase write staging (pending_ops) + append-only audit_log
// ---------------------------------------------------------------------------

// Mirrors the per-tenant pending_ops table verbatim (spec 007). App-written ISO
// timestamps as TEXT keep turn-window comparisons clock-skew-free; integer
// booleans where NULL means "verdict pending".
export const pendingOps = pgTable("pending_ops", {
  opToken: text("op_token").primaryKey(),
  operationType: text("operation_type").notNull(),
  args: text("args").notNull(),
  utterance: text("utterance"),
  productName: text("product_name"),
  candidateCount: integer("candidate_count"),
  turnNonce: text("turn_nonce"),
  auto: integer("auto"),
  requiresHumanReview: integer("requires_human_review"),
  status: text("status").notNull().default("PENDING"),
  commitResult: text("commit_result"),
  reasons: text("reasons"),
  createdAt: text("created_at").notNull(),
  committedAt: text("committed_at"),
});

// Append-only audit of every write the app executes (port of tool_audit). The
// app never UPDATEs or DELETEs a row here.
export const auditLog = pgTable("audit_log", {
  id: bigserial("id", { mode: "number" }).primaryKey(),
  name: text("name").notNull(),
  args: text("args"),
  caller: text("caller"),
  opToken: text("op_token"),
  outcome: text("outcome").notNull(),
  createdAt: text("created_at").notNull(),
});

// The server-authenticated operator-turn record (spec 009 M5 / D-052). Append-only.
// Grounding for the auto-post verdict (lib/verdict.ts) runs against THIS record of the
// operator's own turns in the active flow, never against the client-supplied transcript:
// the server writes each inbound operator message here itself, so a forged turn in the
// request body can never launder an ungrounded amount onto the auto path (AC10). It is
// lighter than a full conversation store: operator utterances for one flow only, keyed by
// a flow_nonce the server echoes to the client, which rotates it when the flow closes.
// The app never UPDATEs or DELETEs a row here.
//
// `owner` binds the record to the authenticated operator (session email), so "the
// operator's OWN turns" is enforced as the same principal, not merely "whatever was
// written under this nonce" — every read and write filters by (owner, flow_nonce). A
// server-side TTL (lib/flow-turns.ts) bounds grounding to the recent active flow, so a
// stale or client-pinned nonce can never accumulate an unbounded corpus. The unique
// (flow_nonce, seq) index makes the append-sequence collision-safe.
export const operatorTurns = pgTable("operator_turns", {
  id: bigserial("id", { mode: "number" }).primaryKey(),
  owner: text("owner"),
  flowNonce: text("flow_nonce").notNull(),
  seq: integer("seq").notNull(),
  text: text("text").notNull(),
  createdAt: text("created_at").notNull(),
}, (t) => ({
  // Unique on the real per-owner key (council: Tamir) so the app-derived seq is collision-
  // safe and two owners can never collide on a shared nonce; the leftmost (owner,flow_nonce)
  // prefix also serves the scoped reads.
  flowSeqUq: uniqueIndex("operator_turns_owner_flow_seq_uq").on(t.owner, t.flowNonce, t.seq),
}));
