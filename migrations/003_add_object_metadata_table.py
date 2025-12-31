"""
Database migration: Add object_metadata table for Vision 31 (Structured Metadata & Context)

Creates table to store contextual metadata for tracked objects:
- track_id: Reference to tracks table
- camera_id: Camera where object was detected
- zone_id: Current zone (entrance, showroom, service_area, etc.)
- zone_enter_time: When object entered the zone
- zone_exit_time: When object exited the zone
- zone_dwell_time: Time spent in the zone (seconds)
- total_dwell_time: Total time in camera view (seconds)
- camera_location: Physical location of camera
- metadata_json: Additional metadata (JSON format)
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def migrate(db_path: str):
    """
    Create object_metadata table and zone_events table.
    
    Args:
        db_path: Path to SQLite database
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create object_metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS object_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                camera_id TEXT NOT NULL,
                zone_id TEXT,
                zone_enter_time REAL,
                zone_exit_time REAL,
                zone_dwell_time REAL,
                total_dwell_time REAL,
                camera_location TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for fast queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_metadata_track
            ON object_metadata(track_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_metadata_zone
            ON object_metadata(zone_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_metadata_camera_zone
            ON object_metadata(camera_id, zone_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_metadata_zone_time
            ON object_metadata(zone_id, zone_enter_time)
        """)
        
        # Create zone_events table for tracking zone entry/exit events
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS zone_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                camera_id TEXT NOT NULL,
                zone_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp REAL NOT NULL,
                bbox TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for zone_events
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_zone_events_track
            ON zone_events(track_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_zone_events_camera_zone
            ON zone_events(camera_id, zone_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_zone_events_timestamp
            ON zone_events(timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_zone_events_type
            ON zone_events(event_type)
        """)
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Migration complete: object_metadata and zone_events tables created")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        return False


def rollback(db_path: str):
    """
    Rollback migration by dropping tables.
    
    Args:
        db_path: Path to SQLite database
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("DROP TABLE IF EXISTS zone_events")
        cursor.execute("DROP TABLE IF NOT EXISTS object_metadata")
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Rollback complete: object_metadata and zone_events tables dropped")
        return True
        
    except Exception as e:
        logger.error(f"❌ Rollback failed: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python 003_add_object_metadata_table.py <db_path> [rollback]")
        sys.exit(1)
    
    db_path = sys.argv[1]
    
    if len(sys.argv) > 2 and sys.argv[2] == 'rollback':
        success = rollback(db_path)
    else:
        success = migrate(db_path)
    
    sys.exit(0 if success else 1)

