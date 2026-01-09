#!/usr/bin/env python3
"""
Diagnose PostgreSQL encoding issues.
"""
import os
import sys
from dotenv import load_dotenv
import psycopg2

load_dotenv()

print("=" * 60)
print("PostgreSQL Encoding Diagnostics")
print("=" * 60)
print()

# Connection parameters
params = {
    'host': os.getenv("POSTGRES_HOST", "localhost"),
    'port': int(os.getenv("POSTGRES_PORT", "5432")),
    'dbname': os.getenv("POSTGRES_DB", "beansco_main"),
    'user': os.getenv("POSTGRES_USER", "beansco"),
    'password': os.getenv("POSTGRES_PASSWORD", "changeme123"),
}

print("Connection parameters:")
for key, value in params.items():
    if key == 'password':
        print(f"  {key}: ***")
    else:
        print(f"  {key}: {value}")
print()

# Try different encoding configurations
encodings_to_try = [
    {},  # Default
    {'client_encoding': 'UTF8'},
    {'client_encoding': 'LATIN1'},
    {'client_encoding': 'SQL_ASCII'},
]

for i, extra_params in enumerate(encodings_to_try):
    test_params = {**params, **extra_params}
    encoding_name = extra_params.get('client_encoding', 'default')

    print(f"Test {i+1}: Trying with encoding: {encoding_name}")

    try:
        conn = psycopg2.connect(**test_params)
        cur = conn.cursor()

        # Get server encoding
        cur.execute("SHOW SERVER_ENCODING")
        server_enc = cur.fetchone()[0]

        # Get client encoding
        cur.execute("SHOW CLIENT_ENCODING")
        client_enc = cur.fetchone()[0]

        # Get database encoding
        cur.execute("SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname = %s", (params['dbname'],))
        db_enc = cur.fetchone()[0]

        print(f"  ✓ Connection successful!")
        print(f"    Server encoding: {server_enc}")
        print(f"    Client encoding: {client_enc}")
        print(f"    Database encoding: {db_enc}")
        print()

        cur.close()
        conn.close()

        print("=" * 60)
        print("SOLUTION FOUND!")
        print("=" * 60)
        print(f"Use client_encoding='{encoding_name}' in your connection")
        print()
        sys.exit(0)

    except UnicodeDecodeError as e:
        print(f"  ✗ UnicodeDecodeError: {e}")
        print()
    except psycopg2.Error as e:
        print(f"  ✗ PostgreSQL error: {e}")
        print()
    except Exception as e:
        print(f"  ✗ Error: {e}")
        print()

print("=" * 60)
print("No working encoding found!")
print("=" * 60)
print()
print("Possible solutions:")
print("1. Fix PostgreSQL server encoding on VPS")
print("2. Recreate database with UTF8 encoding:")
print("   DROP DATABASE beansco_main;")
print("   CREATE DATABASE beansco_main ENCODING 'UTF8' LC_COLLATE='en_US.UTF-8' LC_CTYPE='en_US.UTF-8';")
print()
