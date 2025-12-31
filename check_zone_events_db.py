import sqlite3

conn = sqlite3.connect('recordings.db')
cursor = conn.cursor()

# Check zone_events table
print("Zone Events in Database:")
print("=" * 80)

cursor.execute("""
    SELECT track_id, camera_id, zone_id, event_type, timestamp 
    FROM zone_events 
    ORDER BY timestamp DESC 
    LIMIT 10
""")

events = cursor.fetchall()
print(f"Total events: {len(events)}\n")

for event in events:
    track_id, camera_id, zone_id, event_type, timestamp = event
    print(f"Track {track_id}: {event_type} in zone '{zone_id}' (camera: {camera_id})")
    print(f"  Timestamp: {timestamp}\n")

conn.close()

