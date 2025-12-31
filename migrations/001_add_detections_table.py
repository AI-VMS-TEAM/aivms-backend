"""
Migration: Add detections table for Vision 29 (Object Detection)

Creates the detections table to store YOLO detection results.
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)


def migrate(db_path: str):
    """
    Create detections table.
    
    Args:
        db_path: Path to SQLite database
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create detections table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                class TEXT NOT NULL,
                confidence REAL NOT NULL,
                bbox TEXT NOT NULL,
                frame_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (camera_id) REFERENCES cameras(id)
            )
        """)
        
        # Create indexes for fast queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_detections_camera_timestamp
            ON detections(camera_id, timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_detections_class
            ON detections(class)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_detections_confidence
            ON detections(confidence)
        """)
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Migration complete: detections table created")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python 001_add_detections_table.py <db_path>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    success = migrate(db_path)
    sys.exit(0 if success else 1)

