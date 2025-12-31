"""
Database migration: Add tracks table for Vision 30 (Object Tracking)

Creates table to store closed tracks with metadata:
- track_id: Unique track identifier
- camera_id: Camera where track was detected
- class: Object class (person, vehicle, etc.)
- enter_time: When object entered frame
- exit_time: When object left frame
- dwell_time: Total time in frame (seconds)
- frames_seen: Number of frames object was detected
- last_bbox: Final bounding box
- last_confidence: Final confidence score
"""

import sqlite3
import sys
from pathlib import Path


def create_tracks_table(db_path: str):
    """Create tracks table with proper schema and indexes."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tracks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER NOT NULL,
            camera_id TEXT NOT NULL,
            class TEXT NOT NULL,
            enter_time REAL NOT NULL,
            exit_time REAL NOT NULL,
            dwell_time REAL NOT NULL,
            frames_seen INTEGER NOT NULL,
            last_bbox TEXT NOT NULL,
            last_confidence REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (camera_id) REFERENCES cameras(id)
        )
    """)
    
    # Create indexes for fast queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracks_camera_time 
        ON tracks(camera_id, enter_time)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracks_class 
        ON tracks(class)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracks_dwell_time 
        ON tracks(dwell_time)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tracks_track_id 
        ON tracks(track_id)
    """)
    
    conn.commit()
    conn.close()
    
    print("✅ tracks table created successfully")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python 002_add_tracks_table.py <db_path>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)
    
    try:
        create_tracks_table(db_path)
        print(f"✅ Migration completed for {db_path}")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)

