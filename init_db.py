import os
import sqlite3

DB_PATH = os.getenv("SQLITE_PATH", "beansco.db")
SQL_FILE = "schema_and_dummy.sql"

def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        sql = f.read()

    conn.executescript(sql)
    conn.commit()
    conn.close()
    print(f"✅ Created SQLite database at: {DB_PATH}")

if __name__ == "__main__":
    main()
