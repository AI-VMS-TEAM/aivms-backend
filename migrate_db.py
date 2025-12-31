#!/usr/bin/env python3
"""
Database migration script to upgrade schema with millisecond precision
"""

import sqlite3
import os
import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = "storage/recordings/recordings.db"
BACKUP_PATH = "storage/recordings/recordings.db.backup"

def migrate_database():
    """Migrate database to new schema with millisecond precision."""

    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return False

    try:
        # Create backup
        if os.path.exists(BACKUP_PATH):
            os.remove(BACKUP_PATH)
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"✓ Backup created: {BACKUP_PATH}")

        # Connect to database with timeout
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute('PRAGMA journal_mode=WAL')
        cursor = conn.cursor()
        
        # Check if start_time_ms column already exists
        cursor.execute("PRAGMA table_info(recordings)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'start_time_ms' in columns:
            print("✓ Database already has start_time_ms column")
            conn.close()
            return True
        
        print("Migrating database schema...")

        # Drop new table if it exists from previous failed attempt
        cursor.execute('DROP TABLE IF EXISTS recordings_new')
        print("✓ Cleaned up any previous migration attempts")

        # Create new table with updated schema
        cursor.execute('''
            CREATE TABLE recordings_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                camera_name TEXT NOT NULL,
                segment_path TEXT NOT NULL UNIQUE,
                start_time DATETIME NOT NULL,
                start_time_ms INTEGER NOT NULL,
                end_time DATETIME,
                duration_ms INTEGER,
                file_size INTEGER,
                codec TEXT,
                resolution TEXT,
                bitrate INTEGER,
                keyframe_count INTEGER,
                is_valid BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(camera_id, start_time_ms)
            )
        ''')
        print("✓ Created new recordings table")
        
        # Copy data from old table with unique start_time_ms
        # If multiple segments have the same millisecond, add sequence number
        cursor.execute('''
            INSERT INTO recordings_new
            (id, camera_id, camera_name, segment_path, start_time, start_time_ms,
             end_time, duration_ms, file_size, codec, resolution, bitrate,
             keyframe_count, is_valid, created_at)
            SELECT
                id, camera_id, camera_name, segment_path, start_time,
                CAST(strftime('%s', start_time) * 1000 AS INTEGER) +
                    (ROW_NUMBER() OVER (PARTITION BY camera_id, CAST(strftime('%s', start_time) * 1000 AS INTEGER) ORDER BY id) - 1),
                end_time, duration_ms, file_size, codec, resolution, bitrate,
                keyframe_count, is_valid, created_at
            FROM recordings
        ''')
        print("✓ Migrated data to new table")
        
        # Drop old table
        cursor.execute('DROP TABLE recordings')
        print("✓ Dropped old recordings table")
        
        # Rename new table
        cursor.execute('ALTER TABLE recordings_new RENAME TO recordings')
        print("✓ Renamed new table to recordings")
        
        # Recreate indexes
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_camera_time 
            ON recordings(camera_id, start_time_ms)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_start_time 
            ON recordings(start_time_ms)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_camera_id 
            ON recordings(camera_id)
        ''')
        print("✓ Recreated indexes")
        
        conn.commit()
        conn.close()
        
        print("\n✅ Database migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        if os.path.exists(BACKUP_PATH):
            print(f"Restoring from backup...")
            shutil.copy2(BACKUP_PATH, DB_PATH)
            print("✓ Restored from backup")
        return False

if __name__ == "__main__":
    success = migrate_database()
    exit(0 if success else 1)

