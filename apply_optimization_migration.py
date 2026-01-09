#!/usr/bin/env python3
"""
Apply performance optimization migration to PostgreSQL.

This script adds the get_all_tenant_stats() function to the database,
which dramatically improves the performance of loading the tenant list.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Load environment variables
load_dotenv()


def get_db_connection():
    """Create a direct PostgreSQL connection with explicit encoding."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "beansco_main"),
        user=os.getenv("POSTGRES_USER", "beansco"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme123"),
        # Explicit encoding configuration
        client_encoding='UTF8',
        options='-c client_encoding=UTF8'
    )


def apply_migration():
    """Apply the tenant stats optimization migration."""
    print("[MIGRATION] Applying tenant stats optimization...")

    # Read migration file
    migration_file = Path(__file__).parent / "postgres" / "migrations" / "add_tenant_stats_function.sql"

    if not migration_file.exists():
        print(f"[ERROR] Migration file not found: {migration_file}")
        sys.exit(1)

    with open(migration_file, 'r', encoding='utf-8') as f:
        migration_sql = f.read()

    conn = None
    try:
        # Connect to database with explicit encoding
        print("[MIGRATION] Connecting to PostgreSQL...")
        conn = get_db_connection()
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        cur = conn.cursor()

        # Execute the migration SQL
        print("[MIGRATION] Executing SQL migration...")
        cur.execute(migration_sql)

        cur.close()

        print("[MIGRATION] ✓ Migration applied successfully!")
        print("[MIGRATION] The get_all_tenant_stats() function has been created.")
        print("[MIGRATION] Backend will now use optimized queries for loading tenant list.")

    except psycopg2.Error as e:
        print(f"[ERROR] PostgreSQL error: {e}")
        print(f"[ERROR] Error code: {e.pgcode}")
        if hasattr(e, 'pgerror'):
            print(f"[ERROR] Details: {e.pgerror}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to apply migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if conn:
            conn.close()


def verify_function():
    """Verify that the function was created successfully."""
    print("\n[VERIFY] Testing the new function...")

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM get_all_tenant_stats()")
        stats = cur.fetchall()

        # Get column names
        colnames = [desc[0] for desc in cur.description]

        cur.close()

        print(f"[VERIFY] ✓ Function works! Found stats for {len(stats)} tenant(s):")
        for row in stats:
            # Convert tuple to dict using column names
            row_dict = dict(zip(colnames, row))
            print(f"  - Schema: {row_dict['schema_name']}")
            print(f"    Products: {row_dict['products_count']}, Sales: {row_dict['sales_count']}")
            print(f"    Revenue: ${row_dict['revenue_cents']/100:.2f}, Profit: ${row_dict['profit_usd']:.2f}")

    except Exception as e:
        print(f"[VERIFY] ⚠ Could not test function: {e}")
        print("[VERIFY] This is OK if you have no tenant data yet.")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    # Check that we're using PostgreSQL
    use_postgres = os.getenv("USE_POSTGRES", "false").lower() == "true"

    if not use_postgres:
        print("[ERROR] This migration is only for PostgreSQL.")
        print("[ERROR] Set USE_POSTGRES=true in your .env file first.")
        sys.exit(1)

    print("=" * 60)
    print("TENANT STATS OPTIMIZATION MIGRATION")
    print("=" * 60)
    print()
    print("This will add a new PostgreSQL function that:")
    print("  - Queries all tenant schemas in a single call")
    print("  - Reduces N+1 queries to 1 query")
    print("  - Dramatically improves tenant list loading speed")
    print()

    # Apply migration
    apply_migration()

    # Verify it works
    verify_function()

    print()
    print("=" * 60)
    print("MIGRATION COMPLETE!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Restart your backend server")
    print("  2. Visit http://localhost:8000/ to see the optimized tenant list")
    print("  3. The page should load MUCH faster now!")
    print()
