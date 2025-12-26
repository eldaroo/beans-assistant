import sqlite3
import os

DB_PATH = os.getenv("SQLITE_PATH", "beansco.db")

conn = sqlite3.connect(DB_PATH)
with open("views.sql") as f:
    conn.executescript(f.read())
conn.commit()
conn.close()
