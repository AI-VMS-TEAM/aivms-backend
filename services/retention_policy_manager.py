"""
Retention Policy Manager
Manages per-camera retention policies and cleanup history
"""

import logging
import sqlite3
from datetime import datetime
from threading import Lock

logger = logging.getLogger(__name__)


class RetentionPolicyManager:
    """
    Manages per-camera retention policies.
    
    Features:
    - Per-camera retention configuration
    - Policy persistence in database
    - Cleanup history tracking
    - Emergency cleanup thresholds
    """
    
    def __init__(self, index_db):
        """
        Initialize retention policy manager.
        
        Args:
            index_db: RecordingIndex instance
        """
        self.index_db = index_db
        self.lock = Lock()
        
        logger.info("RetentionPolicyManager initialized")
    
    def get_policy(self, camera_id):
        """
        Get retention policy for a camera.
        
        Args:
            camera_id: Camera identifier
            
        Returns:
            Policy dict or None if not found
        """
        try:
            conn = self.index_db._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, camera_id, retention_days, min_free_space_gb,
                       emergency_cleanup_threshold, created_at, updated_at
                FROM retention_policies
                WHERE camera_id = ?
            ''', (camera_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'id': row[0],
                    'camera_id': row[1],
                    'retention_days': row[2],
                    'min_free_space_gb': row[3],
                    'emergency_cleanup_threshold': row[4],
                    'created_at': row[5],
                    'updated_at': row[6]
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get policy for {camera_id}: {e}")
            return None
    
    def get_all_policies(self):
        """
        Get all retention policies.
        
        Returns:
            List of policy dicts
        """
        try:
            conn = self.index_db._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, camera_id, retention_days, min_free_space_gb,
                       emergency_cleanup_threshold, created_at, updated_at
                FROM retention_policies
                ORDER BY camera_id
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            policies = []
            for row in rows:
                policies.append({
                    'id': row[0],
                    'camera_id': row[1],
                    'retention_days': row[2],
                    'min_free_space_gb': row[3],
                    'emergency_cleanup_threshold': row[4],
                    'created_at': row[5],
                    'updated_at': row[6]
                })
            
            return policies
            
        except Exception as e:
            logger.error(f"Failed to get all policies: {e}")
            return []
    
    def create_or_update_policy(self, camera_id, retention_days=30,
                                min_free_space_gb=50, emergency_cleanup_threshold=0.90):
        """
        Create or update a retention policy.

        Args:
            camera_id: Camera identifier
            retention_days: Days to keep recordings (7-90)
            min_free_space_gb: Minimum free space to maintain
            emergency_cleanup_threshold: Disk usage threshold for emergency cleanup (0.0-1.0)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate inputs
            retention_days = max(7, min(retention_days, 90))  # Clamp 7-90
            min_free_space_gb = max(10, min(min_free_space_gb, 500))  # Min 10GB, max 500GB
            emergency_cleanup_threshold = max(0.80, min(emergency_cleanup_threshold, 0.99))  # 80-99%
            
            with self.lock:
                conn = self.index_db._get_connection()
                cursor = conn.cursor()
                
                # Check if policy exists
                cursor.execute('SELECT id FROM retention_policies WHERE camera_id = ?', (camera_id,))
                exists = cursor.fetchone() is not None
                
                if exists:
                    # Update existing policy
                    cursor.execute('''
                        UPDATE retention_policies
                        SET retention_days = ?, min_free_space_gb = ?,
                            emergency_cleanup_threshold = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE camera_id = ?
                    ''', (retention_days, min_free_space_gb, emergency_cleanup_threshold, camera_id))
                    logger.info(f"Updated policy for {camera_id}: {retention_days} days")
                else:
                    # Create new policy
                    cursor.execute('''
                        INSERT INTO retention_policies
                        (camera_id, retention_days, min_free_space_gb, emergency_cleanup_threshold)
                        VALUES (?, ?, ?, ?)
                    ''', (camera_id, retention_days, min_free_space_gb, emergency_cleanup_threshold))
                    logger.info(f"Created policy for {camera_id}: {retention_days} days")
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            logger.error(f"Failed to create/update policy for {camera_id}: {e}")
            return False
    
    def delete_policy(self, camera_id):
        """
        Delete a retention policy.
        
        Args:
            camera_id: Camera identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.lock:
                conn = self.index_db._get_connection()
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM retention_policies WHERE camera_id = ?', (camera_id,))
                conn.commit()
                conn.close()
                
                logger.info(f"Deleted policy for {camera_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete policy for {camera_id}: {e}")
            return False
    
    def record_cleanup(self, camera_id, deleted_segments, freed_space_bytes, cleanup_type='scheduled'):
        """
        Record a cleanup operation in history.
        
        Args:
            camera_id: Camera identifier
            deleted_segments: Number of segments deleted
            freed_space_bytes: Space freed in bytes
            cleanup_type: 'scheduled' or 'emergency'
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.lock:
                conn = self.index_db._get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO cleanup_history
                    (camera_id, deleted_segments, freed_space_bytes, cleanup_type)
                    VALUES (?, ?, ?, ?)
                ''', (camera_id, deleted_segments, freed_space_bytes, cleanup_type))
                
                conn.commit()
                conn.close()
                
                logger.info(f"Recorded {cleanup_type} cleanup for {camera_id}: "
                           f"{deleted_segments} segments, {freed_space_bytes / (1024**3):.2f} GB freed")
                return True
                
        except Exception as e:
            logger.error(f"Failed to record cleanup for {camera_id}: {e}")
            return False
    
    def get_cleanup_history(self, camera_id=None, limit=100):
        """
        Get cleanup history.
        
        Args:
            camera_id: Optional camera filter
            limit: Maximum records to return
            
        Returns:
            List of cleanup history records
        """
        try:
            conn = self.index_db._get_connection()
            cursor = conn.cursor()
            
            if camera_id:
                cursor.execute('''
                    SELECT id, camera_id, deleted_segments, freed_space_bytes,
                           cleanup_type, timestamp
                    FROM cleanup_history
                    WHERE camera_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (camera_id, limit))
            else:
                cursor.execute('''
                    SELECT id, camera_id, deleted_segments, freed_space_bytes,
                           cleanup_type, timestamp
                    FROM cleanup_history
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            history = []
            for row in rows:
                history.append({
                    'id': row[0],
                    'camera_id': row[1],
                    'deleted_segments': row[2],
                    'freed_space_bytes': row[3],
                    'freed_space_gb': row[3] / (1024**3),
                    'cleanup_type': row[4],
                    'timestamp': row[5]
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Failed to get cleanup history: {e}")
            return []

