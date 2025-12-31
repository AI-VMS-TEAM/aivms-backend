"""
Retention Manager for Recording Storage
Handles automatic cleanup and rolling retention policy
"""

import os
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from services.retention_policy_manager import RetentionPolicyManager

logger = logging.getLogger(__name__)


class RetentionManager:
    """
    Manages recording retention and automatic cleanup.

    Features:
    - Rolling retention (7-90 days configurable)
    - Automatic cleanup of old segments
    - Disk space monitoring
    - Graceful cleanup on shutdown
    """
    
    def __init__(self, index_db, storage_path, retention_days=30, cleanup_interval_hours=1):
        """
        Initialize retention manager.

        Args:
            index_db: RecordingIndex instance
            storage_path: Base storage path
            retention_days: Days to keep recordings (7-90)
            cleanup_interval_hours: How often to run cleanup
        """
        self.index_db = index_db
        self.storage_path = Path(storage_path)
        self.retention_days = max(7, min(retention_days, 90))  # Clamp 7-90 (was 30-90, now fixed!)
        self.cleanup_interval_hours = cleanup_interval_hours

        # Initialize policy manager
        self.policy_manager = RetentionPolicyManager(index_db)

        self.cleanup_thread = None
        self.is_running = False

        logger.info(
            f"RetentionManager initialized: {self.retention_days} days retention, "
            f"cleanup every {self.cleanup_interval_hours} hour(s)"
        )
    
    def start_cleanup_thread(self):
        """Start the automatic cleanup thread."""
        if self.is_running:
            logger.warning("Cleanup thread already running")
            return
        
        self.is_running = True
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="RetentionCleanupThread"
        )
        self.cleanup_thread.start()
        logger.info("Retention cleanup thread started")
    
    def stop_cleanup_thread(self):
        """Stop the automatic cleanup thread."""
        logger.info("Stopping retention cleanup thread...")
        self.is_running = False
        
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)
        
        logger.info("Retention cleanup thread stopped")
    
    def _cleanup_loop(self):
        """Main cleanup loop that runs periodically."""
        # Defer first cleanup by 5 minutes to avoid database locks during startup
        logger.info("Deferring first cleanup by 5 minutes to avoid startup conflicts...")
        initial_delay = 300  # 5 minutes
        for _ in range(initial_delay):
            if not self.is_running:
                return
            time.sleep(1)

        while self.is_running:
            try:
                # Run cleanup
                self.cleanup_old_recordings()

                # Sleep for configured interval
                sleep_seconds = self.cleanup_interval_hours * 3600
                for _ in range(sleep_seconds):
                    if not self.is_running:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
                time.sleep(60)  # Wait before retrying
    
    def cleanup_old_recordings(self):
        """
        Delete recordings older than retention period.
        Optimized with batch deletion and progress logging.
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)

            logger.info(f"Running cleanup: removing recordings before {cutoff_date}")

            # Get old segments from database
            old_segments = self.index_db.get_old_segments(cutoff_date)

            if not old_segments:
                logger.debug("No old segments to clean up")
                return

            total_segments = len(old_segments)
            logger.info(f"Found {total_segments:,} segments to delete")

            deleted_count = 0
            freed_space = 0
            failed_count = 0
            batch_size = 1000
            segment_paths_to_delete = []

            for i, segment in enumerate(old_segments):
                segment_path = segment['segment_path']

                try:
                    # Delete file from disk
                    if os.path.exists(segment_path):
                        file_size = os.path.getsize(segment_path)
                        os.remove(segment_path)
                        freed_space += file_size
                        deleted_count += 1
                        segment_paths_to_delete.append(segment_path)

                    # Batch delete from database for performance
                    if len(segment_paths_to_delete) >= batch_size:
                        self.index_db.delete_segments_batch(segment_paths_to_delete)
                        segment_paths_to_delete = []

                        # Log progress every batch
                        progress_pct = (i + 1) / total_segments * 100
                        freed_mb = freed_space / (1024*1024)
                        logger.info(
                            f"Cleanup progress: {i+1:,}/{total_segments:,} ({progress_pct:.1f}%) - "
                            f"Deleted: {deleted_count:,}, Failed: {failed_count}, Freed: {freed_mb:.1f} MB"
                        )

                except Exception as e:
                    logger.error(f"Failed to delete segment {segment_path}: {e}")
                    failed_count += 1

            # Delete remaining segments from database
            if segment_paths_to_delete:
                self.index_db.delete_segments_batch(segment_paths_to_delete)

            logger.info(
                f"Cleanup completed: deleted {deleted_count:,} segments, "
                f"failed {failed_count}, freed {freed_space / (1024*1024):.2f} MB"
            )

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def get_storage_stats(self):
        """Get storage usage statistics."""
        try:
            total_size = 0
            total_files = 0
            
            for root, dirs, files in os.walk(self.storage_path):
                for file in files:
                    if file.endswith('.mp4'):
                        filepath = os.path.join(root, file)
                        total_size += os.path.getsize(filepath)
                        total_files += 1
            
            return {
                'total_files': total_files,
                'total_size_bytes': total_size,
                'total_size_gb': total_size / (1024**3),
                'retention_days': self.retention_days
            }
            
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {}
    
    def estimate_storage_needed(self, bitrate_mbps=5, cameras=4):
        """
        Estimate storage needed for retention period.
        
        Args:
            bitrate_mbps: Average bitrate per camera in Mbps
            cameras: Number of cameras
        
        Returns:
            Estimated storage in GB
        """
        # Calculate bytes per second per camera
        bytes_per_second = (bitrate_mbps * 1_000_000) / 8
        
        # Calculate for all cameras
        total_bytes_per_second = bytes_per_second * cameras
        
        # Calculate for retention period
        seconds_in_period = self.retention_days * 24 * 3600
        total_bytes = total_bytes_per_second * seconds_in_period
        
        # Convert to GB
        total_gb = total_bytes / (1024**3)
        
        return total_gb
    
    def force_cleanup(self, before_date=None):
        """
        Force cleanup of recordings before a specific date.
        Optimized with batch deletion and progress logging.

        Args:
            before_date: datetime object (default: now - retention_days)
        """
        if before_date is None:
            before_date = datetime.now() - timedelta(days=self.retention_days)

        logger.info(f"Force cleanup: removing recordings before {before_date}")

        try:
            old_segments = self.index_db.get_old_segments(before_date)

            if not old_segments:
                logger.info("No segments to delete")
                return

            total_segments = len(old_segments)
            logger.info(f"Found {total_segments:,} segments to delete")

            deleted_count = 0
            failed_count = 0
            freed_space = 0
            batch_size = 1000
            segment_paths_to_delete = []

            for i, segment in enumerate(old_segments):
                segment_path = segment['segment_path']

                try:
                    if os.path.exists(segment_path):
                        file_size = os.path.getsize(segment_path)
                        os.remove(segment_path)
                        freed_space += file_size
                        deleted_count += 1
                        segment_paths_to_delete.append(segment_path)

                    # Batch delete from database for performance
                    if len(segment_paths_to_delete) >= batch_size:
                        self.index_db.delete_segments_batch(segment_paths_to_delete)
                        segment_paths_to_delete = []

                        # Log progress every batch
                        progress_pct = (i + 1) / total_segments * 100
                        freed_mb = freed_space / (1024*1024)
                        logger.info(
                            f"Force cleanup progress: {i+1:,}/{total_segments:,} ({progress_pct:.1f}%) - "
                            f"Deleted: {deleted_count:,}, Failed: {failed_count}, Freed: {freed_mb:.1f} MB"
                        )

                except Exception as e:
                    logger.error(f"Failed to delete {segment_path}: {e}")
                    failed_count += 1

            # Delete remaining segments from database
            if segment_paths_to_delete:
                self.index_db.delete_segments_batch(segment_paths_to_delete)

            logger.info(
                f"Force cleanup completed: deleted {deleted_count:,} segments, "
                f"failed {failed_count}, freed {freed_space / (1024*1024):.2f} MB"
            )

        except Exception as e:
            logger.error(f"Force cleanup failed: {e}")
    
    def get_retention_info(self):
        """Get retention policy information."""
        return {
            'retention_days': self.retention_days,
            'cleanup_interval_hours': self.cleanup_interval_hours,
            'is_running': self.is_running,
            'storage_stats': self.get_storage_stats()
        }

