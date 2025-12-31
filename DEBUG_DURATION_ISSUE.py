#!/usr/bin/env python3
"""
Debug script to investigate the duration calculation issue
"""

import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('recordings.db')
cursor = conn.cursor()

# Query for 11/13/2025 last hour (23:00 - 00:00)
start_time = datetime(2025, 11, 13, 23, 0, 0)
end_time = datetime(2025, 11, 14, 0, 0, 0)

print(f"Querying for: {start_time} to {end_time}")
print(f"Query range: {start_time.isoformat()} to {end_time.isoformat()}")
print()

# Get all segments in this range
cursor.execute('''
    SELECT camera_id, start_time, end_time, duration_ms, segment_path
    FROM recordings
    WHERE start_time >= ? AND end_time <= ?
    ORDER BY camera_id, start_time
''', (start_time.isoformat(), end_time.isoformat()))

rows = cursor.fetchall()
print(f"Total segments found: {len(rows)}")
print()

# Group by camera
cameras = {}
for camera_id, start, end, duration_ms, path in rows:
    if camera_id not in cameras:
        cameras[camera_id] = []
    cameras[camera_id].append({
        'start': start,
        'end': end,
        'duration_ms': duration_ms,
        'path': path
    })

# Analyze each camera
for camera_id, segments in cameras.items():
    print(f"\n{'='*80}")
    print(f"Camera: {camera_id}")
    print(f"Segments: {len(segments)}")
    
    if segments:
        first_seg = segments[0]
        last_seg = segments[-1]
        
        first_start = datetime.fromisoformat(first_seg['start'])
        last_start = datetime.fromisoformat(last_seg['start'])
        last_end = datetime.fromisoformat(last_seg['end'])
        
        # Calculate duration as PlaybackManager does
        calculated_duration = (last_end - first_start).total_seconds()
        
        print(f"First segment start: {first_start}")
        print(f"Last segment start: {last_start}")
        print(f"Last segment end: {last_end}")
        print(f"Calculated duration: {calculated_duration} seconds = {calculated_duration/3600:.2f} hours")
        print(f"Expected duration: 3600 seconds = 1.0 hours")
        print()
        
        # Show first and last few segments
        print("First 3 segments:")
        for i, seg in enumerate(segments[:3]):
            print(f"  {i+1}. {seg['start']} -> {seg['end']} ({seg['duration_ms']}ms)")
        
        print("...")
        print("Last 3 segments:")
        for i, seg in enumerate(segments[-3:]):
            print(f"  {len(segments)-2+i}. {seg['start']} -> {seg['end']} ({seg['duration_ms']}ms)")

conn.close()

