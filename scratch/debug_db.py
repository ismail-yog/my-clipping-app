import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

from database import Database

def debug_db():
    db = Database()
    print("=== StreamClipper Job Stats ===")
    stats = db.get_stats()
    print(f"Stats: {stats}")
    
    print("\n=== Recent Jobs ===")
    # Query database for recent jobs
    with db._conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, job_type, clip_id, status, error, retries, created_at FROM jobs ORDER BY id DESC LIMIT 10")
        columns = [col[0] for col in cursor.description]
        for row in cursor.fetchall():
            d = dict(zip(columns, row))
            print(f"Job #{d['id']}: type={d['job_type']}, status={d['status']}, retries={d['retries']}, error={d['error']}, created={d['created_at']}")
        
    print("\n=== Recent Clips ===")
    clips = db.get_clips(limit=5)
    for c in clips:
        print(f"Clip {c['clip_id']} ({c['streamer_name']}): status={c['status']}, title={c['title']}")
        
    db.close()

if __name__ == "__main__":
    debug_db()
