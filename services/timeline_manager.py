"""
Timeline Manager - Builds and maintains timeline index for fast scrubber navigation
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from threading import Lock
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class TimelineManager:
    """Manages timeline index for efficient recording navigation"""
    
    def __init__(self, index_db):
        """
        Initialize TimelineManager
        
        Args:
            index_db: RecordingIndex instance for database access
        """
        self.index_db = index_db
        self.db_path = index_db.db_path
        self.lock = Lock()
        logger.info("TimelineManager initialized")
    
    def build_timeline(self, camera_id: str, start_date: datetime, end_date: datetime) -> bool:
        """
        Build timeline index for a camera in date range
        
        Args:
            camera_id: Camera identifier
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Get all segments for camera in date range
                query = '''
                    SELECT 
                        camera_id, start_time, end_time, duration_ms, file_size
                    FROM recordings
                    WHERE camera_id = ? 
                        AND DATE(start_time) >= ? 
                        AND DATE(start_time) <= ?
                        AND is_valid = 1
                    ORDER BY start_time ASC
                '''
                
                cursor.execute(query, (camera_id, start_date.date(), end_date.date()))
                segments = cursor.fetchall()
                
                # Group segments by date and hour
                timeline_buckets = {}
                for segment in segments:
                    cam_id, start_time_str, end_time_str, duration_ms, file_size = segment
                    start_time = datetime.fromisoformat(start_time_str)
                    
                    date_key = start_time.date()
                    hour_key = start_time.hour
                    bucket_key = (date_key, hour_key)
                    
                    if bucket_key not in timeline_buckets:
                        timeline_buckets[bucket_key] = {
                            'segment_count': 0,
                            'total_duration_ms': 0,
                            'total_size_bytes': 0,
                            'first_segment_time': start_time,
                            'last_segment_time': start_time
                        }
                    
                    bucket = timeline_buckets[bucket_key]
                    bucket['segment_count'] += 1
                    bucket['total_duration_ms'] += duration_ms or 0
                    bucket['total_size_bytes'] += file_size or 0
                    bucket['last_segment_time'] = start_time
                
                # Insert/update timeline index
                for (date_key, hour_key), data in timeline_buckets.items():
                    cursor.execute('''
                        INSERT OR REPLACE INTO timeline_index
                        (camera_id, date, hour, segment_count, total_duration_ms, 
                         total_size_bytes, first_segment_time, last_segment_time, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (
                        camera_id,
                        date_key,
                        hour_key,
                        data['segment_count'],
                        data['total_duration_ms'],
                        data['total_size_bytes'],
                        data['first_segment_time'],
                        data['last_segment_time']
                    ))
                
                conn.commit()
                conn.close()
                
                logger.info(f"Built timeline for {camera_id}: {len(timeline_buckets)} buckets")
                return True
                
        except Exception as e:
            logger.error(f"Failed to build timeline for {camera_id}: {e}", exc_info=True)
            return False
    
    def update_timeline(self, camera_id: str, segment: Dict) -> bool:
        """
        Update timeline when new segment is indexed
        
        Args:
            camera_id: Camera identifier
            segment: Segment dict with start_time, duration_ms, file_size
        
        Returns:
            True if successful, False otherwise
        """
        try:
            start_time = segment.get('start_time')
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time)
            
            date_key = start_time.date()
            hour_key = start_time.hour
            
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Check if bucket exists
                cursor.execute('''
                    SELECT id, segment_count, total_duration_ms, total_size_bytes
                    FROM timeline_index
                    WHERE camera_id = ? AND date = ? AND hour = ?
                ''', (camera_id, date_key, hour_key))
                
                row = cursor.fetchone()
                
                if row:
                    # Update existing bucket
                    bucket_id, seg_count, total_duration, total_size = row
                    cursor.execute('''
                        UPDATE timeline_index
                        SET segment_count = ?,
                            total_duration_ms = ?,
                            total_size_bytes = ?,
                            last_segment_time = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (
                        seg_count + 1,
                        total_duration + (segment.get('duration_ms') or 0),
                        total_size + (segment.get('file_size') or 0),
                        start_time,
                        bucket_id
                    ))
                else:
                    # Create new bucket
                    cursor.execute('''
                        INSERT INTO timeline_index
                        (camera_id, date, hour, segment_count, total_duration_ms,
                         total_size_bytes, first_segment_time, last_segment_time)
                        VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                    ''', (
                        camera_id,
                        date_key,
                        hour_key,
                        segment.get('duration_ms') or 0,
                        segment.get('file_size') or 0,
                        start_time,
                        start_time
                    ))
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            logger.error(f"Failed to update timeline for {camera_id}: {e}", exc_info=True)
            return False
    
    def get_timeline(self, camera_id: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Get timeline buckets for scrubber
        
        Args:
            camera_id: Camera identifier
            start_date: Start date
            end_date: End date
        
        Returns:
            List of timeline buckets
        """
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = '''
                    SELECT *
                    FROM timeline_index
                    WHERE camera_id = ? 
                        AND date >= ? 
                        AND date <= ?
                    ORDER BY date ASC, hour ASC
                '''
                
                cursor.execute(query, (camera_id, start_date.date(), end_date.date()))
                rows = cursor.fetchall()
                conn.close()
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get timeline for {camera_id}: {e}")
            return []
    
    def get_hourly_summary(self, camera_id: str, date: datetime) -> List[Dict]:
        """
        Get hourly breakdown for a specific date
        
        Args:
            camera_id: Camera identifier
            date: Date to query
        
        Returns:
            List of hourly summaries
        """
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                query = '''
                    SELECT hour, segment_count, total_duration_ms, total_size_bytes, has_motion
                    FROM timeline_index
                    WHERE camera_id = ? AND date = ?
                    ORDER BY hour ASC
                '''
                
                cursor.execute(query, (camera_id, date.date()))
                rows = cursor.fetchall()
                conn.close()
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get hourly summary for {camera_id}: {e}")
            return []

