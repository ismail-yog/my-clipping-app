import sqlite3
import urllib.request
import json
import os

# 1. Update status to uploaded
db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "streamclipper.db"))
print(f"Connecting to database to set status to 'uploaded': {db_path}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("UPDATE clips SET status = 'uploaded' WHERE clip_id = 'vod_testvod_0'")
conn.commit()
print("Set status of vod_testvod_0 to 'uploaded'")

# Verify update
cursor.execute("SELECT status FROM clips WHERE clip_id = 'vod_testvod_0'")
print("Current DB status before API call:", cursor.fetchone()[0])
conn.close()

# 2. Call the approve API
url = "http://localhost:8000/api/clips/vod_testvod_0/approve"
print(f"Sending POST request to {url}")
req = urllib.request.Request(url, method="POST")
try:
    with urllib.request.urlopen(req) as response:
        resp_data = json.loads(response.read().decode('utf-8'))
        print("API Response:", resp_data)
except Exception as e:
    print("API Request failed:", e)

# 3. Verify status in database again (should still be uploaded)
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT status FROM clips WHERE clip_id = 'vod_testvod_0'")
print("Current DB status after API call:", cursor.fetchone()[0])
conn.close()
