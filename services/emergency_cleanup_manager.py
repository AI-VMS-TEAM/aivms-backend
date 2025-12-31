"""
Emergency Cleanup Manager
Handles emergency cleanup when disk usage exceeds critical threshold
"""

import logging
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class EmergencyCleanupManager:
    """
    Manages emergency cleanup when disk usage is critical.
    
    Features:
    - Monitors disk usage from HealthMonitor
    - Triggers emergency cleanup at 90%+ disk usage
    - Aggressively deletes oldest segments
    - Creates alerts for emergency cleanup
    - Prevents multiple concurrent cleanups
    """
    
    def __init__(self, health_monitor, retention_manager, retention_policy_manager, index_db):
        """
        Initialize emergency cleanup manager.
        
        Args:
            health_monitor: HealthMonitor instance
            retention_manager: RetentionManager instance
            retention_policy_manager: RetentionPolicyManager instance
            index_db: RecordingIndex instance
        """
        self.health_monitor = health_monitor
        self.retention_manager = retention_manager
        self.retention_policy_manager = retention_policy_manager
        self.index_db = index_db
        
        self.is_running = False
        self.monitor_thread = None
        self.last_emergency_cleanup = {}  # camera_id -> timestamp
        self.emergency_cleanup_cooldown_seconds = 300  # 5 minutes between cleanups per camera
        
        logger.info("EmergencyCleanupManager initialized")
    
    def start(self):
        """Start the emergency cleanup monitor thread."""
        if self.is_running:
            logger.warning("Emergency cleanup monitor already running")
            return
        
        self.is_running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="EmergencyCleanupMonitorThread"
        )
        self.monitor_thread.start()
        logger.info("Emergency cleanup monitor started")
    
    def stop(self):
        """Stop the emergency cleanup monitor thread."""
        logger.info("Stopping emergency cleanup monitor...")
        self.is_running = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        logger.info("Emergency cleanup monitor stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop that checks disk usage periodically."""
        while self.is_running:
            try:
                # Check disk usage every 30 seconds
                self._check_and_cleanup()
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Emergency cleanup monitor error: {e}")
                time.sleep(60)
    
    def _check_and_cleanup(self):
        """Check disk usage and trigger emergency cleanup if needed."""
        try:
            if not self.health_monitor:
                return

            # Get current disk usage
            disk_metrics = self.health_monitor.get_disk_metrics()
            if not disk_metrics:
                return

            # Handle both dict and object types
            if hasattr(disk_metrics, 'percent_used'):
                percent_used = disk_metrics.percent_used / 100.0
            else:
                percent_used = disk_metrics.get('percent_used', 0) / 100.0
            
            # Check if emergency cleanup is needed
            if percent_used >= 0.90:
                logger.warning(f"Disk usage critical: {percent_used*100:.1f}% - Triggering emergency cleanup")
                self._trigger_emergency_cleanup()
            
        except Exception as e:
            logger.error(f"Error checking disk usage: {e}")
    
    def _trigger_emergency_cleanup(self):
        """Trigger emergency cleanup for all cameras."""
        try:
            policies = self.retention_policy_manager.get_all_policies()
            
            if not policies:
                logger.warning("No retention policies found for emergency cleanup")
                return
            
            total_freed = 0
            total_deleted = 0
            
            # Sort by retention days (delete from cameras with longest retention first)
            policies_sorted = sorted(policies, key=lambda p: p['retention_days'], reverse=True)
            
            for policy in policies_sorted:
                camera_id = policy['camera_id']
                
                # Check cooldown
                last_cleanup = self.last_emergency_cleanup.get(camera_id, 0)
                time_since_cleanup = time.time() - last_cleanup
                
                if time_since_cleanup < self.emergency_cleanup_cooldown_seconds:
                    logger.debug(f"Skipping {camera_id} - in cooldown period")
                    continue
                
                # Trigger aggressive cleanup (delete 2x normal retention)
                aggressive_days = max(1, policy['retention_days'] // 2)
                deleted, freed = self._cleanup_camera(camera_id, aggressive_days, 'emergency')
                
                total_deleted += deleted
                total_freed += freed
                self.last_emergency_cleanup[camera_id] = time.time()
                
                # Check if we've freed enough space
                if self.health_monitor:
                    disk_metrics = self.health_monitor.get_disk_metrics()
                    if disk_metrics:
                        if hasattr(disk_metrics, 'percent_used'):
                            percent_used = disk_metrics.percent_used / 100.0
                        else:
                            percent_used = disk_metrics.get('percent_used', 0) / 100.0
                        if percent_used < 0.85:  # Stop when below 85%
                            logger.info(f"Emergency cleanup complete: freed {total_freed / (1024**3):.2f} GB")
                            break
            
            # Create alert
            if self.health_monitor:
                self.health_monitor._create_alert(
                    alert_type='emergency_cleanup',
                    severity='critical',
                    message=f"Emergency cleanup triggered: deleted {total_deleted} segments, freed {total_freed / (1024**3):.2f} GB",
                    metric_value=total_freed
                )
            
        except Exception as e:
            logger.error(f"Emergency cleanup failed: {e}")
    
    def _cleanup_camera(self, camera_id, retention_days, cleanup_type):
        """
        Clean up old segments for a camera.
        
        Args:
            camera_id: Camera identifier
            retention_days: Days to keep
            cleanup_type: 'scheduled' or 'emergency'
            
        Returns:
            Tuple of (deleted_count, freed_bytes)
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            # Get old segments
            old_segments = self.index_db.get_old_segments(cutoff_date, camera_id)
            
            if not old_segments:
                return 0, 0
            
            deleted_count = 0
            freed_space = 0
            
            for segment in old_segments:
                segment_path = segment['segment_path']
                
                try:
                    import os
                    if os.path.exists(segment_path):
                        file_size = os.path.getsize(segment_path)
                        os.remove(segment_path)
                        freed_space += file_size
                        deleted_count += 1
                    
                    # Delete from index
                    self.index_db.delete_segment(segment_path)
                    
                except Exception as e:
                    logger.error(f"Failed to delete {segment_path}: {e}")
            
            # Record cleanup
            if deleted_count > 0:
                self.retention_policy_manager.record_cleanup(
                    camera_id, deleted_count, freed_space, cleanup_type
                )
                logger.info(f"Cleaned up {camera_id}: deleted {deleted_count} segments, "
                           f"freed {freed_space / (1024**3):.2f} GB")
            
            return deleted_count, freed_space
            
        except Exception as e:
            logger.error(f"Cleanup failed for {camera_id}: {e}")
            return 0, 0
    
    def get_status(self):
        """Get emergency cleanup status."""
        try:
            return {
                'is_running': self.is_running,
                'last_cleanups': self.last_emergency_cleanup,
                'cooldown_seconds': self.emergency_cleanup_cooldown_seconds
            }
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return {}

