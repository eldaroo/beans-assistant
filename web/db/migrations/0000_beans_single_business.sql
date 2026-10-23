CREATE TABLE "audit_log" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"args" text,
	"caller" text,
	"op_token" text,
	"outcome" text NOT NULL,
	"created_at" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE "bom_lines" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"product_id" bigint NOT NULL,
	"cost_input_id" bigint NOT NULL,
	"country" varchar(64) NOT NULL,
	"quantity" numeric(18, 4) DEFAULT '1' NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "bom_lines_qty_positive" CHECK ("bom_lines"."quantity" > 0)
);
--> statement-breakpoint
CREATE TABLE "cost_inputs" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"name" varchar(255) NOT NULL,
	"category" varchar(64),
	"unit" varchar(32),
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "customs_duties" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"product_id" bigint NOT NULL,
	"country" varchar(64) NOT NULL,
	"usd_amount_cents" integer,
	"note" text,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "customs_usd_nonneg" CHECK ("customs_duties"."usd_amount_cents" IS NULL OR "customs_duties"."usd_amount_cents" >= 0)
);
--> statement-breakpoint
CREATE TABLE "expenses" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"expense_date" date DEFAULT CURRENT_DATE NOT NULL,
	"category" varchar(50) NOT NULL,
	"description" text,
	"amount_cents" integer NOT NULL,
	"currency" varchar(3) DEFAULT 'USD' NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "expenses_amount_nonneg" CHECK ("expenses"."amount_cents" >= 0)
);
--> statement-breakpoint
CREATE TABLE "indirect_costs" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"country" varchar(64) NOT NULL,
	"period_month" varchar(7) NOT NULL,
	"pool_cents" integer NOT NULL,
	"units_produced" integer,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "indirect_pool_nonneg" CHECK ("indirect_costs"."pool_cents" >= 0)
);
--> statement-breakpoint
CREATE TABLE "input_purchases" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"cost_input_id" bigint NOT NULL,
	"supplier_id" bigint,
	"original_currency" varchar(3) DEFAULT 'USD' NOT NULL,
	"original_amount_cents" integer NOT NULL,
	"fx_rate" numeric(18, 8) DEFAULT '1' NOT NULL,
	"usd_amount_cents" integer NOT NULL,
	"quantity" numeric(18, 4) DEFAULT '1' NOT NULL,
	"purchased_at" date DEFAULT CURRENT_DATE NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "input_purchases_orig_nonneg" CHECK ("input_purchases"."original_amount_cents" >= 0),
	CONSTRAINT "input_purchases_fx_positive" CHECK ("input_purchases"."fx_rate" > 0),
	CONSTRAINT "input_purchases_usd_nonneg" CHECK ("input_purchases"."usd_amount_cents" >= 0),
	CONSTRAINT "input_purchases_qty_positive" CHECK ("input_purchases"."quantity" > 0)
);
--> statement-breakpoint
CREATE TABLE "labor_costs" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"product_id" bigint NOT NULL,
	"country" varchar(64) NOT NULL,
	"batch_payment_cents" integer NOT NULL,
	"units_completed" integer NOT NULL,
	"recorded_at" date DEFAULT CURRENT_DATE NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "labor_payment_nonneg" CHECK ("labor_costs"."batch_payment_cents" >= 0),
	CONSTRAINT "labor_units_nonneg" CHECK ("labor_costs"."units_completed" >= 0)
);
--> statement-breakpoint
CREATE TABLE "landed_cost_snapshots" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"product_id" bigint NOT NULL,
	"country" varchar(64) NOT NULL,
	"materials_cents" integer,
	"labor_cents" integer,
	"packaging_cents" integer,
	"shipping_cents" integer,
	"customs_cents" integer,
	"indirect_cents" integer,
	"total_cents" integer DEFAULT 0 NOT NULL,
	"status" varchar(16) DEFAULT 'parcial' NOT NULL,
	"pending_components" text,
	"computed_at" timestamp DEFAULT now() NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "landed_total_nonneg" CHECK ("landed_cost_snapshots"."total_cents" >= 0),
	CONSTRAINT "landed_status_check" CHECK ("landed_cost_snapshots"."status" IN ('completo','parcial'))
);
--> statement-breakpoint
CREATE TABLE "packaging_costs" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"product_id" bigint NOT NULL,
	"country" varchar(64) NOT NULL,
	"usd_amount_cents" integer NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "packaging_usd_nonneg" CHECK ("packaging_costs"."usd_amount_cents" >= 0)
);
--> statement-breakpoint
CREATE TABLE "pending_ops" (
	"op_token" text PRIMARY KEY NOT NULL,
	"operation_type" text NOT NULL,
	"args" text NOT NULL,
	"utterance" text,
	"product_name" text,
	"candidate_count" integer,
	"turn_nonce" text,
	"auto" integer,
	"requires_human_review" integer,
	"status" text DEFAULT 'PENDING' NOT NULL,
	"commit_result" text,
	"reasons" text,
	"created_at" text NOT NULL,
	"committed_at" text
);
--> statement-breakpoint
CREATE TABLE "production_records" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"product_id" bigint,
	"country" varchar(64) NOT NULL,
	"period_week" varchar(8) NOT NULL,
	"units_produced" integer DEFAULT 0 NOT NULL,
	"units_target" integer,
	"expected_next_at" date,
	"recorded_at" date DEFAULT CURRENT_DATE NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "production_produced_nonneg" CHECK ("production_records"."units_produced" >= 0),
	CONSTRAINT "production_target_nonneg" CHECK ("production_records"."units_target" IS NULL OR "production_records"."units_target" >= 0)
);
--> statement-breakpoint
CREATE TABLE "products" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"sku" varchar(100) NOT NULL,
	"name" varchar(255) NOT NULL,
	"description" text,
	"unit_cost_cents" integer DEFAULT 0 NOT NULL,
	"unit_price_cents" integer,
	"is_active" boolean DEFAULT true NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "products_sku_unique" UNIQUE("sku"),
	CONSTRAINT "check_unit_cost_positive" CHECK ("products"."unit_cost_cents" >= 0),
	CONSTRAINT "check_unit_price_positive" CHECK ("products"."unit_price_cents" IS NULL OR "products"."unit_price_cents" >= 0)
);
--> statement-breakpoint
CREATE TABLE "sale_items" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"sale_id" bigint NOT NULL,
	"product_id" bigint NOT NULL,
	"quantity" integer NOT NULL,
	"unit_price_cents" integer NOT NULL,
	"line_total_cents" integer NOT NULL,
	CONSTRAINT "sale_items_qty_positive" CHECK ("sale_items"."quantity" > 0)
);
--> statement-breakpoint
CREATE TABLE "sales" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"sale_number" varchar(50) NOT NULL,
	"customer_name" varchar(255),
	"status" varchar(20) NOT NULL,
	"currency" varchar(3) DEFAULT 'USD' NOT NULL,
	"total_amount_cents" integer NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"paid_at" timestamp,
	CONSTRAINT "sales_sale_number_unique" UNIQUE("sale_number"),
	CONSTRAINT "sales_status_check" CHECK ("sales"."status" IN ('PAID','PENDING','CANCELLED')),
	CONSTRAINT "sales_total_nonneg" CHECK ("sales"."total_amount_cents" >= 0)
);
--> statement-breakpoint
CREATE TABLE "shipping_lanes" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"product_id" bigint NOT NULL,
	"country" varchar(64) NOT NULL,
	"usd_amount_cents" integer,
	"note" text,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "shipping_usd_nonneg" CHECK ("shipping_lanes"."usd_amount_cents" IS NULL OR "shipping_lanes"."usd_amount_cents" >= 0)
);
--> statement-breakpoint
CREATE TABLE "stock_movements" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"product_id" bigint NOT NULL,
	"movement_type" varchar(20) NOT NULL,
	"quantity" integer NOT NULL,
	"reason" text,
	"reference" varchar(100),
	"occurred_at" timestamp DEFAULT now() NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "stock_movement_type_check" CHECK ("stock_movements"."movement_type" IN ('IN','OUT','ADJUSTMENT')),
	CONSTRAINT "stock_qty_nonzero" CHECK ("stock_movements"."quantity" <> 0)
);
--> statement-breakpoint
CREATE TABLE "suppliers" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"name" varchar(255) NOT NULL,
	"country" varchar(64),
	"contact" varchar(255),
	"is_active" boolean DEFAULT true NOT NULL,
	"last_checkin_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "bom_lines" ADD CONSTRAINT "bom_lines_product_id_products_id_fk" FOREIGN KEY ("product_id") REFERENCES "public"."products"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "bom_lines" ADD CONSTRAINT "bom_lines_cost_input_id_cost_inputs_id_fk" FOREIGN KEY ("cost_input_id") REFERENCES "public"."cost_inputs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "customs_duties" ADD CONSTRAINT "customs_duties_product_id_products_id_fk" FOREIGN KEY ("product_id") REFERENCES "public"."products"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "input_purchases" ADD CONSTRAINT "input_purchases_cost_input_id_cost_inputs_id_fk" FOREIGN KEY ("cost_input_id") REFERENCES "public"."cost_inputs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "input_purchases" ADD CONSTRAINT "input_purchases_supplier_id_suppliers_id_fk" FOREIGN KEY ("supplier_id") REFERENCES "public"."suppliers"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "labor_costs" ADD CONSTRAINT "labor_costs_product_id_products_id_fk" FOREIGN KEY ("product_id") REFERENCES "public"."products"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "landed_cost_snapshots" ADD CONSTRAINT "landed_cost_snapshots_product_id_products_id_fk" FOREIGN KEY ("product_id") REFERENCES "public"."products"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "packaging_costs" ADD CONSTRAINT "packaging_costs_product_id_products_id_fk" FOREIGN KEY ("product_id") REFERENCES "public"."products"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "production_records" ADD CONSTRAINT "production_records_product_id_products_id_fk" FOREIGN KEY ("product_id") REFERENCES "public"."products"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "sale_items" ADD CONSTRAINT "sale_items_sale_id_sales_id_fk" FOREIGN KEY ("sale_id") REFERENCES "public"."sales"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "sale_items" ADD CONSTRAINT "sale_items_product_id_products_id_fk" FOREIGN KEY ("product_id") REFERENCES "public"."products"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "shipping_lanes" ADD CONSTRAINT "shipping_lanes_product_id_products_id_fk" FOREIGN KEY ("product_id") REFERENCES "public"."products"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "stock_movements" ADD CONSTRAINT "stock_movements_product_id_products_id_fk" FOREIGN KEY ("product_id") REFERENCES "public"."products"("id") ON DELETE no action ON UPDATE no action;