"""
Recovery Manager for Recording Engine
Handles crash recovery and file integrity verification
"""

import os
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class RecoveryManager:
    """
    Manages recovery from crashes and power loss.
    
    Features:
    - File integrity verification
    - Index reconstruction from disk
    - Orphaned file cleanup
    - Recovery logging
    """
    
    def __init__(self, index_db, storage_path):
        """
        Initialize recovery manager.
        
        Args:
            index_db: RecordingIndex instance
            storage_path: Base storage path
        """
        self.index_db = index_db
        self.storage_path = Path(storage_path)
        logger.info("RecoveryManager initialized")
    
    def verify_and_recover(self):
        """
        Run full recovery check on startup.
        
        Steps:
        1. Verify all indexed files exist
        2. Find orphaned files on disk
        3. Rebuild index from disk if needed
        4. Mark corrupted files as invalid
        """
        logger.info("Starting recovery verification...")
        
        try:
            # Step 1: Verify indexed files
            self._verify_indexed_files()
            
            # Step 2: Find orphaned files
            self._find_orphaned_files()
            
            # Step 3: Verify file integrity
            self._verify_file_integrity()
            
            logger.info("Recovery verification completed successfully")
            
        except Exception as e:
            logger.error(f"Recovery verification failed: {e}")
    
    def _verify_indexed_files(self):
        """Verify that all indexed files exist on disk."""
        logger.info("Verifying indexed files...")
        
        try:
            # Get all recordings from database
            conn = __import__('sqlite3').connect(str(self.index_db.db_path))
            conn.row_factory = __import__('sqlite3').Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM recordings WHERE is_valid = 1')
            recordings = cursor.fetchall()
            conn.close()
            
            missing_count = 0
            for recording in recordings:
                segment_path = recording['segment_path']
                
                if not os.path.exists(segment_path):
                    logger.warning(f"Missing file: {segment_path}")
                    self.index_db.mark_invalid(segment_path)
                    missing_count += 1
                    
                    # Log recovery event
                    self.index_db.log_recovery_event(
                        recording['camera_id'],
                        'MISSING_FILE',
                        f"File not found: {segment_path}"
                    )
            
            if missing_count > 0:
                logger.warning(f"Found {missing_count} missing files")
            else:
                logger.info("All indexed files verified")
            
        except Exception as e:
            logger.error(f"File verification failed: {e}")
    
    def _find_orphaned_files(self):
        """Find files on disk that are not in the index and recover them."""
        logger.info("Searching for orphaned files...")

        try:
            # Use the index_db's recovery method to find and re-index orphaned files
            # Use a small batch size (100) to avoid database locks during active recording
            recovery_stats = self.index_db.recover_orphaned_files(
                self.storage_path,
                max_batch_size=100  # Small batch to avoid locking
            )

            logger.info(f"Orphaned file recovery results:")
            logger.info(f"  Total orphaned: {recovery_stats['total_orphaned']}")
            logger.info(f"  Recovered: {recovery_stats['recovered']}")
            logger.info(f"  Failed: {recovery_stats['failed']}")
            logger.info(f"  Batch size: {recovery_stats['batch_size']}")

            # If there are still many orphaned files, log a warning
            if recovery_stats['total_orphaned'] > recovery_stats['batch_size']:
                logger.warning(f"⚠️  {recovery_stats['total_orphaned'] - recovery_stats['recovered']} orphaned files remain. Recovery will continue in subsequent runs.")

            if recovery_stats['errors']:
                for error in recovery_stats['errors'][:5]:  # Log first 5 errors
                    logger.warning(f"  Error: {error}")

        except Exception as e:
            logger.error(f"Orphaned file search failed: {e}")
    
    def _verify_file_integrity(self):
        """Verify integrity of recorded files."""
        logger.info("Verifying file integrity...")
        
        try:
            corrupted_count = 0
            
            # Get all valid recordings
            conn = __import__('sqlite3').connect(str(self.index_db.db_path))
            conn.row_factory = __import__('sqlite3').Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM recordings WHERE is_valid = 1')
            recordings = cursor.fetchall()
            conn.close()
            
            for recording in recordings:
                segment_path = recording['segment_path']
                
                if not self._is_file_valid(segment_path):
                    logger.warning(f"Corrupted file: {segment_path}")
                    self.index_db.mark_invalid(segment_path)
                    corrupted_count += 1
                    
                    # Log recovery event
                    self.index_db.log_recovery_event(
                        recording['camera_id'],
                        'CORRUPTED_FILE',
                        f"File failed integrity check: {segment_path}"
                    )
            
            if corrupted_count > 0:
                logger.warning(f"Found {corrupted_count} corrupted files")
            else:
                logger.info("All files passed integrity check")
            
        except Exception as e:
            logger.error(f"File integrity verification failed: {e}")
    
    def _is_file_valid(self, filepath):
        """
        Check if a file is valid (not corrupted).

        Checks:
        - File exists
        - File size > 0
        - File has valid MP4/TS header
        - File is readable
        """
        try:
            # Check existence
            if not os.path.exists(filepath):
                return False

            # Check size
            file_size = os.path.getsize(filepath)
            if file_size < 1024:  # At least 1KB
                return False

            # Check header
            with open(filepath, 'rb') as f:
                header = f.read(8)

            # Valid MP4 headers:
            # - ftyp (file type box) - full MP4 files
            # - moof (movie fragment box) - fragmented MP4 (fMP4) segments
            # - mdat (media data box) - raw media data
            # - free (free space box) - padding
            # Or TS header (0x47)
            if (header[4:8] == b'ftyp' or  # ftyp at offset 4
                header[4:8] == b'moof' or  # moof at offset 4 (fMP4 fragment)
                header[4:8] == b'mdat' or  # mdat at offset 4 (media data)
                header[4:8] == b'free' or  # free at offset 4 (free space)
                header[0:1] == b'\x47'):   # TS header (0x47)
                return True

            return False

        except Exception as e:
            logger.error(f"File validation error for {filepath}: {e}")
            return False
    
    def get_recovery_log(self, camera_id=None, limit=100):
        """Get recovery event log."""
        try:
            conn = __import__('sqlite3').connect(str(self.index_db.db_path))
            conn.row_factory = __import__('sqlite3').Row
            cursor = conn.cursor()
            
            if camera_id:
                cursor.execute(
                    'SELECT * FROM recovery_log WHERE camera_id = ? ORDER BY timestamp DESC LIMIT ?',
                    (camera_id, limit)
                )
            else:
                cursor.execute(
                    'SELECT * FROM recovery_log ORDER BY timestamp DESC LIMIT ?',
                    (limit,)
                )
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Failed to get recovery log: {e}")
            return []

