from database import Database
import json

db = Database()
print("--- JOBS ---")
jobs = db.get_jobs(limit=20)
for j in jobs:
    print(f"ID: {j['id']} Type: {j['job_type']} Status: {j['status']} Error: {j.get('error','')}")
    if j['error']:
        print(f"  Details: {j['error']}")

print("\n--- CLIPS ---")
clips = db.get_clips()
for c in clips[:10]:
    print(f"ID: {c['clip_id']} Title: {c['title']} Status: {c['status']}")

db.close()
