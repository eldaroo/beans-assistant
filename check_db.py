import sqlite3

conn = sqlite3.connect("beansco.db")

rows = conn.execute(
    "SELECT name, type FROM sqlite_master "
    "WHERE type IN ('table','view') "
    "ORDER BY type, name"
).fetchall()

conn.close()

print(rows)
