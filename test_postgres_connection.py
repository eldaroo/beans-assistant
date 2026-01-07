#!/usr/bin/env python3
"""
Test PostgreSQL Connection

Quick script to verify PostgreSQL connection is working correctly.

Usage:
    python test_postgres_connection.py
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("=" * 60)
print("PostgreSQL Connection Test")
print("=" * 60)
print()

# Check environment variables
use_postgres = os.getenv("USE_POSTGRES", "false").lower() == "true"

if not use_postgres:
    print("❌ USE_POSTGRES is not set to 'true' in .env")
    print()
    print("Set USE_POSTGRES=true in your .env file to use PostgreSQL")
    sys.exit(1)

print("✅ USE_POSTGRES=true")
print()

# Check PostgreSQL environment variables
pg_host = os.getenv("POSTGRES_HOST", "localhost")
pg_port = os.getenv("POSTGRES_PORT", "5432")
pg_db = os.getenv("POSTGRES_DB", "beansco_main")
pg_user = os.getenv("POSTGRES_USER", "beansco")
pg_password = os.getenv("POSTGRES_PASSWORD")

print(f"Connection details:")
print(f"  Host: {pg_host}")
print(f"  Port: {pg_port}")
print(f"  Database: {pg_db}")
print(f"  User: {pg_user}")
print(f"  Password: {'***' if pg_password else 'NOT SET'}")
print()

if not pg_password:
    print("⚠️  POSTGRES_PASSWORD is not set in .env")
    print()

# Try to import PostgreSQL module
print("[1/5] Importing database module...")
try:
    from database_config import db
    print("✅ database_config imported successfully")
    print(f"    Using module: {db.__name__}")
except ImportError as e:
    print(f"❌ Failed to import: {e}")
    print()
    print("Install PostgreSQL dependencies:")
    print("  pip install psycopg2-binary")
    sys.exit(1)
print()

# Try to connect
print("[2/5] Testing database connection...")
try:
    result = db.fetch_one("SELECT 1 as test")
    if result and result.get('test') == 1:
        print("✅ Database connection successful")
    else:
        print(f"⚠️  Unexpected result: {result}")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print()
    print("Troubleshooting:")
    print("  1. Is PostgreSQL running? (docker compose ps)")
    print("  2. Is the password correct in .env?")
    print("  3. Is the SSH tunnel active? (ps aux | grep 'ssh -L')")
    print("  4. Can you reach the host? (telnet localhost 5432)")
    sys.exit(1)
print()

# Check tables exist
print("[3/5] Checking database schema...")
try:
    tables = db.fetch_all("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)

    if not tables:
        print("⚠️  No tables found in database")
        print()
        print("Did you run the migration?")
        print("  python migrate_to_postgres.py --db-url '...'")
    else:
        print(f"✅ Found {len(tables)} tables:")
        for table in tables:
            print(f"    - {table['table_name']}")
except Exception as e:
    print(f"⚠️  Could not check tables: {e}")
print()

# Check products
print("[4/5] Checking products table...")
try:
    count = db.fetch_one("SELECT COUNT(*) as count FROM products")
    product_count = count['count'] if count else 0

    if product_count == 0:
        print("⚠️  Products table is empty")
        print()
        print("Run migration to import data:")
        print("  python migrate_to_postgres.py --db-url '...'")
    else:
        print(f"✅ Found {product_count} products")

        # Show sample
        sample = db.fetch_all("SELECT id, sku, name FROM products LIMIT 3")
        if sample:
            print()
            print("Sample products:")
            for prod in sample:
                print(f"    #{prod['id']}: {prod['sku']} - {prod['name']}")
except Exception as e:
    print(f"⚠️  Could not query products: {e}")
print()

# Check views
print("[5/5] Checking database views...")
try:
    views = db.fetch_all("""
        SELECT table_name
        FROM information_schema.views
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)

    if not views:
        print("⚠️  No views found")
    else:
        print(f"✅ Found {len(views)} views:")
        for view in views:
            print(f"    - {view['table_name']}")

        # Test a view
        try:
            profit = db.fetch_one("SELECT profit_usd FROM profit_summary")
            if profit:
                print()
                print(f"Current profit: ${profit['profit_usd']:.2f}")
        except:
            pass

except Exception as e:
    print(f"⚠️  Could not check views: {e}")
print()

# Summary
print("=" * 60)
print("✅ PostgreSQL connection test completed successfully!")
print("=" * 60)
print()
print("Your application is ready to use PostgreSQL.")
print()
print("Next steps:")
print("  1. Start your backend: bash restart_backend.sh")
print("  2. Test API endpoints: curl http://localhost:8000/health")
print("  3. Check docs: http://localhost:8000/docs")
print()
