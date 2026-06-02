import sqlite3
import os

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "streamclipper.db"))
print(f"Connecting to database at {db_path}...")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT clip_id, status, title FROM clips ORDER BY created_at DESC LIMIT 20")
rows = cursor.fetchall()
if not rows:
    print("No clips found in database.")
else:
    print(f"Found {len(rows)} clips:")
    for row in rows:
        title = row['title'].encode('ascii', errors='replace').decode('ascii')
        print(f"  Clip ID: {row['clip_id']} | Status: {row['status']} | Title: {title}")
conn.close()
