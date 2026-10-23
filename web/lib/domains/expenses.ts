// Expenses domain. Ported from backend/services/expenses_service.py.
// REGISTER_EXPENSE is one of the reversible, auto-postable ops. A CANCELACION
// category row is a negative-weighted compensation in the expenses_total view.

import { desc, eq, sql } from "drizzle-orm";
import { db } from "@/lib/db";
import { expenses } from "@/db/schema";
import { centsToUsd } from "@/lib/money";

export type ExpenseRow = typeof expenses.$inferSelect;

export interface ExpenseView extends ExpenseRow {
  amountUsd: number | null;
}

function toView(row: ExpenseRow): ExpenseView {
  return { ...row, amountUsd: centsToUsd(row.amountCents) };
}

export async function listExpenses(opts: { limit?: number; offset?: number } = {}): Promise<ExpenseView[]> {
  const { limit = 100, offset = 0 } = opts;
  const rows = await db
    .select()
    .from(expenses)
    .orderBy(desc(expenses.expenseDate), desc(expenses.id))
    .limit(limit)
    .offset(offset);
  return rows.map(toView);
}

export async function registerExpense(params: {
  amountCents: number;
  description: string;
  category?: string;
  expenseDate?: string | null; // YYYY-MM-DD; defaults to today
  currency?: string;
}): Promise<{ status: string; expense_id: number }> {
  const { amountCents, description, category = "GENERAL", expenseDate = null, currency = "USD" } = params;
  const values: typeof expenses.$inferInsert = {
    amountCents,
    description,
    category,
    currency,
    ...(expenseDate ? { expenseDate } : {}),
  };
  const [row] = await db.insert(expenses).values(values).returning({ id: expenses.id });
  return { status: "ok", expense_id: row.id };
}

// Cancel an expense by appending a CANCELACION compensation of the same amount,
// so the append-only ledger keeps the original row (parity with the Python cancel).
export async function cancelExpense(expenseId: number): Promise<{ status: string; cancellation_id: number }> {
  const [orig] = await db.select().from(expenses).where(eq(expenses.id, expenseId)).limit(1);
  if (!orig) throw new Error(`Expense ${expenseId} not found`);
  const [row] = await db
    .insert(expenses)
    .values({
      amountCents: orig.amountCents,
      description: `Cancelacion de #${expenseId}: ${orig.description ?? ""}`.trim(),
      category: "CANCELACION",
      currency: orig.currency,
    })
    .returning({ id: expenses.id });
  return { status: "ok", cancellation_id: row.id };
}

export async function expensesTotalCents(): Promise<number> {
  const res = await db.execute(sql`SELECT total_expenses_cents FROM expenses_total`);
  return Number((res.rows[0] as { total_expenses_cents: number | string }).total_expenses_cents) || 0;
}
