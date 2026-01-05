"""
Verification script to ensure all profit, revenue, and expense calculations are correct.
"""
import sqlite3
import sys
from pathlib import Path

def verify_database(db_path):
    """Verify calculations in a specific database."""
    print(f"\n{'='*60}")
    print(f"Verificando: {db_path}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # 1. Check revenue calculation
        revenue_view = conn.execute("SELECT * FROM revenue_paid").fetchone()
        revenue_direct = conn.execute(
            "SELECT SUM(total_amount_cents) as total FROM sales WHERE status = 'PAID'"
        ).fetchone()

        print("REVENUE:")
        if revenue_view:
            print(f"  View (revenue_paid): ${revenue_view['revenue_usd']:.2f}")
        else:
            print(f"  View (revenue_paid): NULL (no paid sales)")

        revenue_cents = revenue_direct['total'] if revenue_direct['total'] else 0
        print(f"  Direct query: ${revenue_cents / 100:.2f}")

        if revenue_view:
            expected_revenue = revenue_cents / 100
            actual_revenue = revenue_view['revenue_usd']
            if abs(expected_revenue - actual_revenue) < 0.01:
                print("  [OK] Revenue calculation CORRECT")
            else:
                print(f"  [ERROR] Revenue calculation ERROR: Expected ${expected_revenue:.2f}, got ${actual_revenue:.2f}")

        # 2. Check expenses calculation
        expenses_view = conn.execute("SELECT * FROM expenses_total").fetchone()
        expenses_direct = conn.execute(
            "SELECT SUM(amount_cents) as total FROM expenses"
        ).fetchone()

        print("\nEXPENSES:")
        if expenses_view:
            print(f"  View (expenses_total): ${expenses_view['expenses_usd']:.2f}")
        else:
            print(f"  View (expenses_total): NULL (no expenses)")

        expenses_cents = expenses_direct['total'] if expenses_direct['total'] else 0
        print(f"  Direct query: ${expenses_cents / 100:.2f}")

        if expenses_view:
            expected_expenses = expenses_cents / 100
            actual_expenses = expenses_view['expenses_usd']
            if abs(expected_expenses - actual_expenses) < 0.01:
                print("  [OK] Expenses calculation CORRECT")
            else:
                print(f"  [ERROR] Expenses calculation ERROR: Expected ${expected_expenses:.2f}, got ${actual_expenses:.2f}")

        # 3. Check profit calculation
        profit_view = conn.execute("SELECT * FROM profit_summary").fetchone()

        print("\nPROFIT:")
        if profit_view:
            print(f"  View (profit_summary): ${profit_view['profit_usd']:.2f}")

        # Calculate expected profit
        revenue_usd = revenue_cents / 100 if revenue_cents else 0
        expenses_usd = expenses_cents / 100 if expenses_cents else 0
        expected_profit = revenue_usd - expenses_usd

        print(f"  Expected (revenue - expenses): ${expected_profit:.2f}")
        print(f"    Revenue: ${revenue_usd:.2f}")
        print(f"    Expenses: ${expenses_usd:.2f}")

        if profit_view:
            actual_profit = profit_view['profit_usd']
            if abs(expected_profit - actual_profit) < 0.01:
                print("  [OK] Profit calculation CORRECT")
            else:
                print(f"  [ERROR] Profit calculation ERROR: Expected ${expected_profit:.2f}, got ${actual_profit:.2f}")

        # 4. Check if there are any expenses
        expense_count = conn.execute("SELECT COUNT(*) as count FROM expenses").fetchone()['count']
        print(f"\nEXPENSE RECORDS:")
        print(f"  Total expenses in DB: {expense_count}")

        if expense_count > 0:
            print("\n  Recent expenses:")
            recent = conn.execute("""
                SELECT id, description, amount_cents/100.0 as amount_usd, expense_date, created_at
                FROM expenses
                ORDER BY created_at DESC
                LIMIT 5
            """).fetchall()

            for exp in recent:
                print(f"    ID {exp['id']}: {exp['description']} - ${exp['amount_usd']:.2f} ({exp['expense_date']})")

        # 5. Summary
        print(f"\n{'='*60}")
        print("RESUMEN:")
        print(f"  Revenue: ${revenue_usd:.2f}")
        print(f"  Expenses: ${expenses_usd:.2f}")
        print(f"  Profit: ${expected_profit:.2f}")

        if expected_profit >= 0:
            print(f"  Estado: [OK] GANANCIA")
        else:
            print(f"  Estado: [!] PERDIDA")
        print(f"{'='*60}\n")

    finally:
        conn.close()


if __name__ == "__main__":
    # Check main database
    if Path("beansco.db").exists():
        verify_database("beansco.db")

    # Check multi-tenant databases
    clients_dir = Path("data/clients")
    if clients_dir.exists():
        for client_dir in clients_dir.iterdir():
            if client_dir.is_dir():
                db_path = client_dir / "business.db"
                if db_path.exists():
                    verify_database(str(db_path))
