CREATE TABLE "operator_turns" (
	"id" bigserial PRIMARY KEY NOT NULL,
	"owner" text,
	"flow_nonce" text NOT NULL,
	"seq" integer NOT NULL,
	"text" text NOT NULL,
	"created_at" text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX "operator_turns_owner_flow_seq_uq" ON "operator_turns" USING btree ("owner","flow_nonce","seq");