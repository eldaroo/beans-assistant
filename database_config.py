"""
Database configuration selector.

This module automatically selects between SQLite and PostgreSQL
based on environment variables.

Usage:
    from database_config import db

    # Use the database module
    result = db.fetch_all("SELECT * FROM products")
    db.register_sale(sale_data)

Environment Variables:
    USE_POSTGRES=true       - Enable PostgreSQL
    POSTGRES_HOST           - PostgreSQL host (default: localhost)
    POSTGRES_PORT           - PostgreSQL port (default: 5432)
    POSTGRES_DB             - Database name (default: beansco_main)
    POSTGRES_USER           - Database user (default: beansco)
    POSTGRES_PASSWORD       - Database password (required)
    POSTGRES_SCHEMA         - Schema name for multi-tenant (default: public)
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def get_database_module():
    """
    Get the appropriate database module based on environment configuration.

    Returns:
        module: Either database (SQLite) or database_pg (PostgreSQL)
    """
    use_postgres = os.getenv("USE_POSTGRES", "false").lower() == "true"

    if use_postgres:
        print("[DB CONFIG] Using PostgreSQL")
        try:
            import database_pg as db_module
            return db_module
        except ImportError as e:
            print(f"[DB CONFIG] ❌ Failed to import database_pg: {e}")
            print("[DB CONFIG] Install PostgreSQL dependencies: pip install psycopg2-binary")
            sys.exit(1)
    else:
        print("[DB CONFIG] Using SQLite")
        import database as db_module
        return db_module


# Export the selected database module
db = get_database_module()

# Re-export all functions for convenience
fetch_one = db.fetch_one
fetch_all = db.fetch_all
register_product = db.register_product
add_stock = db.add_stock
remove_stock = db.remove_stock
register_expense = db.register_expense
register_sale = db.register_sale
get_last_sale = db.get_last_sale
get_last_expense = db.get_last_expense
get_last_stock_movement = db.get_last_stock_movement
get_last_operation = db.get_last_operation
cancel_sale = db.cancel_sale
cancel_expense = db.cancel_expense
cancel_stock_movement = db.cancel_stock_movement
deactivate_product = db.deactivate_product
