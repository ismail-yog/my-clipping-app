import sqlite3
import time

db_path = r"C:\Users\ismai\.gemini\antigravity\scratch\streamclipper\streamclipper.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

streamers = [
    ("IShowSpeed", "youtube", "UCWsDFcIhY2DBi3GB5uykGXA", "https://www.youtube.com/@IShowSpeed"),
    ("Kai Cenat", "twitch", "kaicenat", "https://www.twitch.tv/kaicenat"),
    ("Adin Ross", "kick", "adinross", "https://www.kick.com/adinross"),
    ("Jinnytty", "twitch", "jinnytty", "https://www.twitch.tv/jinnytty"),
    ("JakenbakeLIVE", "twitch", "jakenbakeLIVE", "https://www.twitch.tv/jakenbakeLIVE"),
    ("n3on", "kick", "n3on", "https://www.kick.com/n3on"),
    ("Ice Poseidon", "kick", "iceposeidon", "https://www.kick.com/iceposeidon"),
    ("ExtraEmily", "twitch", "extraemily", "https://www.twitch.tv/extraemily"),
    ("Robcdee", "twitch", "robcdee", "https://www.twitch.tv/robcdee"),
    ("CookSux", "twitch", "cooksux", "https://www.twitch.tv/cooksux"),
]

now = time.time()
for name, platform, channel, url in streamers:
    cursor = conn.execute("SELECT id FROM streamers WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        conn.execute(
            "UPDATE streamers SET platform = ?, channel = ?, url = ?, enabled = 1, updated_at = ? WHERE id = ?",
            (platform, channel, url, now, row["id"])
        )
        print(f"Updated: {name}")
    else:
        conn.execute(
            "INSERT INTO streamers (name, platform, channel, url, enabled, auto_approve, created_at, updated_at) VALUES (?, ?, ?, ?, 1, 0, ?, ?)",
            (name, platform, channel, url, now, now)
        )
        print(f"Inserted: {name}")

# Disable other default streamers that were removed
all_names = [s[0] for s in streamers]
cursor = conn.execute("SELECT id, name FROM streamers")
for row in cursor.fetchall():
    if row["name"] not in all_names:
        conn.execute("UPDATE streamers SET enabled = 0, updated_at = ? WHERE id = ?", (now, row["id"]))
        print(f"Disabled old streamer: {row['name']}")

conn.commit()
conn.close()
print("Synchronization complete!")
