"""
Recording Index Database Manager
Manages SQLite database for recording metadata and fast lookups
"""

import sqlite3
import logging
import threading
import queue
import time
import os
from datetime import datetime
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)


class RecordingIndex:
    """
    SQLite-based index for recording metadata.
    Provides fast lookups by timestamp and camera.
    """
    
    def __init__(self, db_path):
        """Initialize database connection."""
        self.db_path = db_path
        self.lock = Lock()
        self.db_timeout = 60.0  # 60 second timeout for database operations

        # Database write queue to avoid concurrent writes
        self.write_queue = queue.Queue()
        self.is_running = True
        self.writer_thread = threading.Thread(
            target=self._database_writer_loop,
            daemon=True,
            name="DatabaseWriterThread"
        )
        self.writer_thread.start()

        self._init_database()

    def _get_connection(self):
        """Get a database connection with proper timeout."""
        return sqlite3.connect(self.db_path, timeout=self.db_timeout)

    def _database_writer_loop(self):
        """
        Background thread that processes all database writes from a queue.
        This ensures only one thread writes to the database at a time,
        avoiding SQLite locking issues.
        """
        logger.info("Database writer thread started")
        conn = self._get_connection()

        while self.is_running:
            try:
                # Get write operation from queue with timeout
                try:
                    operation = self.write_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                if operation is None:  # Shutdown signal
                    break

                # Execute the write operation
                op_type, args, kwargs = operation
                cursor = conn.cursor()

                try:
                    if op_type == 'insert_recording':
                        cursor.execute(args[0], args[1])
                        conn.commit()
                    elif op_type == 'delete_recording':
                        cursor.execute(args[0], args[1])
                        conn.commit()
                    elif op_type == 'update_recording':
                        cursor.execute(args[0], args[1])
                        conn.commit()
                except sqlite3.IntegrityError as e:
                    logger.warning(f"Integrity error during write: {e}")
                    conn.rollback()
                except Exception as e:
                    logger.error(f"Error during database write: {e}")
                    conn.rollback()

                self.write_queue.task_done()

            except Exception as e:
                logger.error(f"Database writer loop error: {e}")
                time.sleep(0.1)

        conn.close()
        logger.info("Database writer thread stopped")

    def _init_database(self):
        """Create database tables if they don't exist."""
        with self.lock:
            conn = self._get_connection()
            # Enable WAL mode for better concurrent access
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            cursor = conn.cursor()

            # Recordings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS recordings (
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
            
            # Create indexes for fast queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_camera_time 
                ON recordings(camera_id, start_time)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_start_time 
                ON recordings(start_time)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_camera_id 
                ON recordings(camera_id)
            ''')
            
            # Retention policies table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS retention_policies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT UNIQUE NOT NULL,
                    retention_days INTEGER DEFAULT 30,
                    min_free_space_gb INTEGER DEFAULT 50,
                    emergency_cleanup_threshold REAL DEFAULT 0.90,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Cleanup history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cleanup_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    deleted_segments INTEGER,
                    freed_space_bytes INTEGER,
                    cleanup_type TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Recovery log table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS recovery_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    event_type TEXT,
                    details TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Timeline index table (for fast timeline scrubber queries)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS timeline_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    date DATE NOT NULL,
                    hour INTEGER NOT NULL,
                    segment_count INTEGER DEFAULT 0,
                    total_duration_ms INTEGER DEFAULT 0,
                    total_size_bytes INTEGER DEFAULT 0,
                    has_motion BOOLEAN DEFAULT 0,
                    first_segment_time DATETIME,
                    last_segment_time DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(camera_id, date, hour)
                )
            ''')

            # Create indexes for timeline queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timeline_camera_date
                ON timeline_index(camera_id, date)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timeline_camera_hour
                ON timeline_index(camera_id, date, hour)
            ''')

            # Motion events table (for future motion detection)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS motion_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME NOT NULL,
                    confidence REAL,
                    region TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_motion_camera_time
                ON motion_events(camera_id, start_time)
            ''')

            conn.commit()
            conn.close()
            logger.info(f"Database initialized: {self.db_path}")
    
    def add_recording(self, camera_id, camera_name, segment_path,
                     start_time, duration_ms, file_size,
                     codec=None, resolution=None, bitrate=None, keyframe_count=None,
                     start_time_ms=None):
        """
        Add a recording segment to the index via queue.
        This method queues the write operation to avoid concurrent database access.

        Args:
            camera_id: Camera identifier
            camera_name: Human-readable camera name
            segment_path: Path to the segment file
            start_time: Start datetime
            duration_ms: Duration in milliseconds
            file_size: File size in bytes
            codec: Video codec (optional)
            resolution: Video resolution (optional)
            bitrate: Bitrate in kbps (optional)
            keyframe_count: Number of keyframes (optional)
            start_time_ms: Start time in milliseconds (optional, auto-calculated if not provided)

        Returns:
            True if queued successfully, False otherwise
        """
        try:
            # Use millisecond precision for unique constraint
            if start_time_ms is None:
                start_time_ms = int(start_time.timestamp() * 1000)

            # Calculate end time
            end_time = datetime.fromtimestamp(
                start_time.timestamp() + (duration_ms / 1000)
            )

            # Queue the write operation
            sql = '''
                INSERT INTO recordings
                (camera_id, camera_name, segment_path, start_time, start_time_ms, end_time,
                 duration_ms, file_size, codec, resolution, bitrate, keyframe_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            params = (
                camera_id, camera_name, segment_path, start_time, start_time_ms, end_time,
                duration_ms, file_size, codec, resolution, bitrate, keyframe_count
            )

            self.write_queue.put(('insert_recording', (sql, params), {}))
            logger.debug(f"Queued recording: {camera_id} - {segment_path} (start_time_ms: {start_time_ms})")
            return True

        except Exception as e:
            logger.error(f"Failed to queue recording for {camera_id} ({segment_path}): {e}", exc_info=True)
            return False
    
    def get_segments(self, camera_id, start_time=None, end_time=None, limit=None):
        """
        Get segments for a camera in time range.

        Args:
            camera_id: Camera identifier
            start_time: Start datetime (optional)
            end_time: End datetime (optional)
            limit: Max results (optional)

        Returns:
            List of segment records
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                query = 'SELECT * FROM recordings WHERE camera_id = ? AND is_valid = 1'
                params = [camera_id]

                if start_time:
                    query += ' AND start_time >= ?'
                    params.append(start_time)

                if end_time:
                    query += ' AND start_time < ?'
                    params.append(end_time)

                query += ' ORDER BY start_time ASC'

                if limit:
                    query += f' LIMIT {limit}'

                cursor.execute(query, params)
                rows = cursor.fetchall()
                conn.close()

                return [dict(row) for row in rows]

            except Exception as e:
                logger.error(f"Failed to get segments: {e}")
                return []
    
    def get_segment_by_timestamp(self, camera_id, timestamp):
        """Get segment containing a specific timestamp."""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM recordings 
                    WHERE camera_id = ? 
                    AND start_time <= ? 
                    AND end_time >= ?
                    AND is_valid = 1
                    LIMIT 1
                ''', (camera_id, timestamp, timestamp))
                
                row = cursor.fetchone()
                conn.close()
                
                return dict(row) if row else None
                
            except Exception as e:
                logger.error(f"Failed to get segment by timestamp: {e}")
                return None
    
    def mark_invalid(self, segment_path):
        """Mark a segment as invalid (corrupted)."""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute(
                    'UPDATE recordings SET is_valid = 0 WHERE segment_path = ?',
                    (segment_path,)
                )
                
                conn.commit()
                conn.close()
                logger.warning(f"Marked segment as invalid: {segment_path}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to mark segment invalid: {e}")
                return False
    
    def delete_segment(self, segment_path):
        """Delete a segment from index."""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute(
                    'DELETE FROM recordings WHERE segment_path = ?',
                    (segment_path,)
                )

                conn.commit()
                conn.close()
                logger.debug(f"Deleted segment from index: {segment_path}")
                return True

            except Exception as e:
                logger.error(f"Failed to delete segment: {e}")
                return False

    def delete_segments_batch(self, segment_paths):
        """
        Delete multiple segments from index in a single transaction.
        Much faster than calling delete_segment() in a loop.

        Args:
            segment_paths: List of segment paths to delete

        Returns:
            Number of segments deleted
        """
        if not segment_paths:
            return 0

        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                # Use executemany for batch deletion
                cursor.executemany(
                    'DELETE FROM recordings WHERE segment_path = ?',
                    [(path,) for path in segment_paths]
                )

                deleted_count = cursor.rowcount
                conn.commit()
                conn.close()

                logger.debug(f"Batch deleted {deleted_count} segments from index")
                return deleted_count

            except Exception as e:
                logger.error(f"Failed to batch delete segments: {e}")
                return 0

    def get_old_segments(self, before_date, camera_id=None):
        """
        Get segments older than a specific date.

        Args:
            before_date: Cutoff datetime
            camera_id: Optional camera filter

        Returns:
            List of segment records
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                if camera_id:
                    cursor.execute('''
                        SELECT * FROM recordings
                        WHERE start_time < ? AND camera_id = ?
                        ORDER BY start_time ASC
                    ''', (before_date, camera_id))
                else:
                    cursor.execute('''
                        SELECT * FROM recordings
                        WHERE start_time < ?
                        ORDER BY start_time ASC
                    ''', (before_date,))

                rows = cursor.fetchall()
                conn.close()

                return [dict(row) for row in rows]

            except Exception as e:
                logger.error(f"Failed to get old segments: {e}")
                return []
    
    def get_camera_stats(self, camera_id):
        """Get recording statistics for a camera."""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total_segments,
                        SUM(file_size) as total_size,
                        MIN(start_time) as earliest,
                        MAX(end_time) as latest,
                        SUM(duration_ms) as total_duration_ms
                    FROM recordings 
                    WHERE camera_id = ? AND is_valid = 1
                ''', (camera_id,))
                
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    return {
                        'total_segments': row[0] or 0,
                        'total_size': row[1] or 0,
                        'earliest': row[2],
                        'latest': row[3],
                        'total_duration_ms': row[4] or 0
                    }
                return {}
                
            except Exception as e:
                logger.error(f"Failed to get camera stats: {e}")
                return {}
    
    def recover_orphaned_files(self, storage_path, max_batch_size=1000):
        """
        Recover orphaned files that exist on disk but aren't indexed in the database.

        Args:
            storage_path: Path to the recordings storage directory
            max_batch_size: Maximum number of files to recover in one batch (default: 1000)

        Returns:
            Dictionary with recovery statistics
        """
        from pathlib import Path
        import os

        stats = {
            'total_orphaned': 0,
            'recovered': 0,
            'failed': 0,
            'errors': [],
            'batch_size': max_batch_size
        }

        try:
            storage_path = Path(storage_path)

            # Get all indexed segment paths
            with self.lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT segment_path FROM recordings')
                indexed_paths = set(row[0] for row in cursor.fetchall())
                conn.close()

            # Find all MP4 files on disk
            mp4_files = list(storage_path.rglob('*.mp4'))
            logger.info(f"Found {len(mp4_files)} MP4 files on disk, {len(indexed_paths)} indexed")

            # Check each file (limit to batch size to avoid overwhelming the database)
            import time
            for idx, file_path in enumerate(mp4_files[:max_batch_size]):
                file_path_str = str(file_path)

                if file_path_str not in indexed_paths:
                    stats['total_orphaned'] += 1

                    try:
                        # Extract camera ID from path
                        parts = file_path.parts
                        if len(parts) >= 3:
                            camera_id = parts[-3]  # Camera folder name

                            # Get file modification time as start_time
                            mtime = os.path.getmtime(file_path)
                            start_time = datetime.fromtimestamp(mtime)
                            start_time_ms = int(mtime * 1000)

                            # Get file size
                            file_size = os.path.getsize(file_path)

                            # Try to index the file
                            success = self.add_recording(
                                camera_id=camera_id,
                                camera_name=camera_id.replace('_', ' ').title(),
                                segment_path=file_path_str,
                                start_time=start_time,
                                start_time_ms=start_time_ms,
                                duration_ms=3000,
                                file_size=file_size
                            )

                            if success:
                                stats['recovered'] += 1
                                logger.info(f"Recovered orphaned file: {file_path.name}")
                            else:
                                stats['failed'] += 1
                                stats['errors'].append(f"Failed to index: {file_path.name}")
                        else:
                            stats['failed'] += 1
                            stats['errors'].append(f"Invalid path: {file_path_str}")

                    except Exception as e:
                        stats['failed'] += 1
                        stats['errors'].append(f"Error: {str(e)}")
                        logger.error(f"Error recovering {file_path}: {e}")

                    # Add small delay every 10 files to avoid database lock
                    if (idx + 1) % 10 == 0:
                        time.sleep(0.1)

            logger.info(f"Recovery complete: {stats['recovered']} recovered, {stats['failed']} failed")
            return stats

        except Exception as e:
            logger.error(f"Failed to recover orphaned files: {e}", exc_info=True)
            stats['errors'].append(f"Recovery failed: {str(e)}")
            return stats

    def log_recovery_event(self, camera_id, event_type, details):
        """Log a recovery event."""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT INTO recovery_log (camera_id, event_type, details)
                    VALUES (?, ?, ?)
                ''', (camera_id, event_type, details))

                conn.commit()
                conn.close()

            except Exception as e:
                logger.error(f"Failed to log recovery event: {e}")

