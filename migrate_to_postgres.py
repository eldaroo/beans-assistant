#!/usr/bin/env python3
"""
Migration script from SQLite to PostgreSQL.

This script migrates data from SQLite databases (multi-tenant) to a single
PostgreSQL database with schema-per-tenant approach.

Usage:
    python migrate_to_postgres.py --db-url postgresql://user:pass@host:5432/dbname
    python migrate_to_postgres.py --db-url postgresql://user:pass@host:5432/dbname --tenant-phone +5491112345678
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any
import json


class PostgreSQLMigrator:
    """Migrates data from SQLite to PostgreSQL."""

    def __init__(self, postgres_url: str):
        """Initialize migrator with PostgreSQL connection."""
        self.postgres_url = postgres_url
        self.pg_conn = None

    def connect_postgres(self):
        """Connect to PostgreSQL."""
        print(f"[POSTGRES] Connecting to database...")
        try:
            self.pg_conn = psycopg2.connect(self.postgres_url)
            self.pg_conn.autocommit = False
            print("[POSTGRES] ✅ Connected successfully")
        except Exception as e:
            print(f"[POSTGRES] ❌ Connection failed: {e}")
            sys.exit(1)

    def migrate_sqlite_to_postgres(self, sqlite_path: str, schema_name: str = "public"):
        """
        Migrate a SQLite database to PostgreSQL schema.

        Args:
            sqlite_path: Path to SQLite database file
            schema_name: PostgreSQL schema name (default: public)
        """
        if not Path(sqlite_path).exists():
            print(f"[ERROR] SQLite database not found: {sqlite_path}")
            return False

        print(f"\n{'='*60}")
        print(f"[MIGRATE] Database: {sqlite_path}")
        print(f"[MIGRATE] Schema: {schema_name}")
        print(f"{'='*60}\n")

        try:
            # Connect to SQLite
            sqlite_conn = sqlite3.connect(sqlite_path)
            sqlite_conn.row_factory = sqlite3.Row
            sqlite_cur = sqlite_conn.cursor()

            pg_cur = self.pg_conn.cursor()

            # Create schema if not exists (for multi-tenant)
            if schema_name != "public":
                pg_cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
                pg_cur.execute(f"SET search_path TO {schema_name}, public")
                print(f"[SCHEMA] Created schema: {schema_name}")

            # Migrate each table
            tables = ["products", "sales", "sale_items", "stock_movements", "expenses"]

            for table in tables:
                self._migrate_table(sqlite_cur, pg_cur, table, schema_name)

            # Commit transaction
            self.pg_conn.commit()
            print(f"\n✅ Migration completed successfully for {sqlite_path}")

            # Close SQLite connection
            sqlite_conn.close()
            return True

        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            self.pg_conn.rollback()
            return False

    def _migrate_table(self, sqlite_cur, pg_cur, table_name: str, schema_name: str):
        """Migrate a single table from SQLite to PostgreSQL."""
        print(f"[{table_name.upper()}] Reading from SQLite...")

        # Get all rows from SQLite
        sqlite_cur.execute(f"SELECT * FROM {table_name}")
        rows = sqlite_cur.fetchall()

        if not rows:
            print(f"[{table_name.upper()}] No data to migrate")
            return

        print(f"[{table_name.upper()}] Found {len(rows)} rows")

        # Get column names (excluding 'id' since it's auto-generated)
        columns = [desc[0] for desc in sqlite_cur.description if desc[0] != 'id']

        # Prepare data for insertion
        data = []
        for row in rows:
            row_dict = dict(row)
            # Convert SQLite boolean (0/1) to PostgreSQL boolean
            if 'is_active' in row_dict:
                row_dict['is_active'] = bool(row_dict['is_active'])

            data.append(tuple(row_dict[col] for col in columns))

        # Build INSERT query
        table_ref = f"{schema_name}.{table_name}" if schema_name != "public" else table_name
        columns_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))

        insert_query = f"""
            INSERT INTO {table_ref} ({columns_str})
            VALUES %s
            ON CONFLICT DO NOTHING
        """

        # Execute batch insert
        execute_values(pg_cur, insert_query, data, template=f"({placeholders})")
        print(f"[{table_name.upper()}] ✅ Migrated {len(data)} rows")

        # Update sequence for SERIAL columns
        pg_cur.execute(f"""
            SELECT setval(
                pg_get_serial_sequence('{table_ref}', 'id'),
                COALESCE((SELECT MAX(id) FROM {table_ref}), 1),
                true
            )
        """)

    def migrate_all_tenants(self, base_path: str = "data/clients"):
        """
        Migrate all tenant databases from data/clients directory.

        Args:
            base_path: Path to clients directory
        """
        clients_dir = Path(base_path)

        if not clients_dir.exists():
            print(f"[ERROR] Clients directory not found: {base_path}")
            return

        # Find all business.db files
        db_files = list(clients_dir.glob("*/business.db"))

        if not db_files:
            print(f"[WARNING] No tenant databases found in {base_path}")
            return

        print(f"\n[TENANTS] Found {len(db_files)} tenant databases\n")

        success_count = 0
        for db_file in db_files:
            # Extract phone number from directory name
            phone = db_file.parent.name

            # Sanitize phone for schema name (remove + and special chars)
            schema_name = f"tenant_{phone.replace('+', '').replace('-', '_')}"

            # Migrate this tenant
            if self.migrate_sqlite_to_postgres(str(db_file), schema_name):
                success_count += 1

        print(f"\n{'='*60}")
        print(f"[SUMMARY] Migrated {success_count}/{len(db_files)} tenants successfully")
        print(f"{'='*60}\n")

    def migrate_main_db(self, sqlite_path: str = "beansco.db"):
        """
        Migrate the main beansco.db database.

        Args:
            sqlite_path: Path to main SQLite database
        """
        return self.migrate_sqlite_to_postgres(sqlite_path, "public")

    def close(self):
        """Close PostgreSQL connection."""
        if self.pg_conn:
            self.pg_conn.close()
            print("[POSTGRES] Connection closed")


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite databases to PostgreSQL")
    parser.add_argument(
        "--db-url",
        required=True,
        help="PostgreSQL connection URL (e.g., postgresql://user:pass@host:5432/dbname)"
    )
    parser.add_argument(
        "--main-db",
        default="beansco.db",
        help="Path to main SQLite database (default: beansco.db)"
    )
    parser.add_argument(
        "--tenants-dir",
        default="data/clients",
        help="Path to tenants directory (default: data/clients)"
    )
    parser.add_argument(
        "--tenant-phone",
        help="Migrate only a specific tenant by phone number (optional)"
    )
    parser.add_argument(
        "--skip-main",
        action="store_true",
        help="Skip migrating the main database"
    )

    args = parser.parse_args()

    # Create migrator
    migrator = PostgreSQLMigrator(args.db_url)
    migrator.connect_postgres()

    try:
        # Migrate main database
        if not args.skip_main:
            print("\n" + "="*60)
            print("MIGRATING MAIN DATABASE")
            print("="*60)
            migrator.migrate_main_db(args.main_db)

        # Migrate specific tenant or all tenants
        if args.tenant_phone:
            tenant_db = Path(args.tenants_dir) / args.tenant_phone / "business.db"
            schema_name = f"tenant_{args.tenant_phone.replace('+', '').replace('-', '_')}"

            print("\n" + "="*60)
            print(f"MIGRATING TENANT: {args.tenant_phone}")
            print("="*60)
            migrator.migrate_sqlite_to_postgres(str(tenant_db), schema_name)
        else:
            print("\n" + "="*60)
            print("MIGRATING ALL TENANTS")
            print("="*60)
            migrator.migrate_all_tenants(args.tenants_dir)

        print("\n✅ Migration process completed!")

    except KeyboardInterrupt:
        print("\n⚠️  Migration interrupted by user")
    finally:
        migrator.close()


if __name__ == "__main__":
    main()
