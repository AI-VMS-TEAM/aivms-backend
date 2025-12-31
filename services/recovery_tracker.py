"""
Recovery Tracker - Monitors recording health and triggers auto-recovery
Detects transient errors and automatically recovers from them
"""

import threading
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import deque

logger = logging.getLogger(__name__)


class RecoveryEvent:
    """Represents a recovery event"""
    def __init__(self, camera_id: str, error_type: str, message: str, recovered: bool = False):
        self.camera_id = camera_id
        self.error_type = error_type  # 'write_failure', 'stream_disconnect', 'file_lock', 'timeout'
        self.message = message
        self.timestamp = time.time()
        self.recovered = recovered
        self.recovery_time = None
    
    def mark_recovered(self):
        """Mark this event as recovered"""
        self.recovered = True
        self.recovery_time = time.time()
    
    def to_dict(self):
        return {
            'camera_id': self.camera_id,
            'error_type': self.error_type,
            'message': self.message,
            'timestamp': self.timestamp,
            'recovered': self.recovered,
            'recovery_time': self.recovery_time,
            'duration_seconds': self.recovery_time - self.timestamp if self.recovered else None
        }


class RecoveryTracker:
    """
    Tracks recording health and manages auto-recovery
    
    Detects:
    - Write failures (disk full, permission denied, file lock)
    - Stream disconnections (network issues, camera offline)
    - Timeouts (slow writes, unresponsive streams)
    - Recording stops (unexpected thread termination)
    
    Actions:
    - Logs errors with severity levels
    - Triggers automatic recovery (reinitialize recorder)
    - Maintains recovery history
    - Generates alerts for dashboard
    """
    
    def __init__(self, health_monitor=None, camera_ids=None, history_size: int = 1000):
        """
        Initialize recovery tracker

        Args:
            health_monitor: Optional HealthMonitor instance for alert generation
            camera_ids: List of camera IDs to track (optional)
            history_size: Number of recovery events to keep in history
        """
        self.health_monitor = health_monitor
        self.history_size = history_size

        # Recovery state
        self.recovery_events = deque(maxlen=history_size)
        self.camera_error_counts = {}  # camera_id -> error count
        self.camera_recovery_counts = {}  # camera_id -> recovery count
        self.camera_last_error_time = {}  # camera_id -> timestamp
        self.camera_last_recovery_time = {}  # camera_id -> last recovery timestamp
        self.lock = threading.Lock()

        # Initialize all cameras with zero counts
        if camera_ids:
            for camera_id in camera_ids:
                self.camera_error_counts[camera_id] = 0
                self.camera_recovery_counts[camera_id] = 0

        # Configuration
        self.error_threshold = 5  # Trigger recovery after N errors
        self.error_window_seconds = 60  # Count errors within this window
        self.recovery_cooldown_seconds = 30  # Wait before attempting recovery again

        logger.info("RecoveryTracker initialized")
    
    def record_error(self, camera_id: str, error_type: str, message: str) -> bool:
        """
        Record an error and determine if recovery should be triggered
        
        Args:
            camera_id: Camera identifier
            error_type: Type of error (write_failure, stream_disconnect, file_lock, timeout)
            message: Error message
            
        Returns:
            True if recovery should be triggered, False otherwise
        """
        with self.lock:
            # Create recovery event
            event = RecoveryEvent(camera_id, error_type, message)
            self.recovery_events.append(event)
            
            # Update error counts
            if camera_id not in self.camera_error_counts:
                self.camera_error_counts[camera_id] = 0
                self.camera_recovery_counts[camera_id] = 0
            
            self.camera_error_counts[camera_id] += 1
            current_time = time.time()
            self.camera_last_error_time[camera_id] = current_time
            
            # Check if we should trigger recovery
            should_recover = self._should_trigger_recovery(camera_id, current_time)
            
            if should_recover:
                logger.warning(f"[{camera_id}] Triggering auto-recovery: {error_type} - {message}")
                self.camera_recovery_counts[camera_id] += 1
                self.camera_last_recovery_time[camera_id] = current_time

                # Create alert if health monitor available
                if self.health_monitor:
                    self.health_monitor._create_alert(
                        alert_type='recovery_triggered',
                        severity='warning',
                        message=f"Auto-recovery triggered for {camera_id}: {error_type}",
                        metric_value=self.camera_error_counts[camera_id]
                    )
            else:
                logger.info(f"[{camera_id}] Error recorded: {error_type} ({self.camera_error_counts[camera_id]}/{self.error_threshold})")
            
            return should_recover
    
    def _should_trigger_recovery(self, camera_id: str, current_time: float) -> bool:
        """Determine if recovery should be triggered"""
        error_count = self.camera_error_counts.get(camera_id, 0)
        last_error_time = self.camera_last_error_time.get(camera_id, 0)
        last_recovery_time = self.camera_last_recovery_time.get(camera_id, 0)

        # Check if we're in the error window
        time_since_last_error = current_time - last_error_time
        if time_since_last_error > self.error_window_seconds:
            # Reset error count if outside window
            self.camera_error_counts[camera_id] = 1
            return False

        # Check if we're in recovery cooldown (prevent multiple recoveries)
        time_since_last_recovery = current_time - last_recovery_time
        if time_since_last_recovery < self.recovery_cooldown_seconds:
            return False

        # Trigger recovery if threshold reached
        return error_count >= self.error_threshold
    
    def mark_recovered(self, camera_id: str):
        """Mark the last error for a camera as recovered"""
        with self.lock:
            # Find and mark the last error event for this camera
            for event in reversed(self.recovery_events):
                if event.camera_id == camera_id and not event.recovered:
                    event.mark_recovered()
                    break
            
            # Reset error count
            self.camera_error_counts[camera_id] = 0
            logger.info(f"[{camera_id}] Recovery successful, error count reset")
            
            # Create alert if health monitor available
            if self.health_monitor:
                self.health_monitor._create_alert(
                    alert_type='recovery_successful',
                    severity='info',
                    message=f"Auto-recovery successful for {camera_id}",
                    metric_value=self.camera_recovery_counts.get(camera_id, 0)
                )
    
    def get_camera_status(self, camera_id: str) -> Dict:
        """Get recovery status for a camera"""
        with self.lock:
            return {
                'camera_id': camera_id,
                'error_count': self.camera_error_counts.get(camera_id, 0),
                'recovery_count': self.camera_recovery_counts.get(camera_id, 0),
                'last_error_time': self.camera_last_error_time.get(camera_id),
                'is_healthy': self.camera_error_counts.get(camera_id, 0) == 0
            }
    
    def get_recovery_history(self, camera_id: str = None, limit: int = 100) -> List[Dict]:
        """Get recovery event history"""
        with self.lock:
            events = list(self.recovery_events)
            
            if camera_id:
                events = [e for e in events if e.camera_id == camera_id]
            
            # Return most recent events first
            return [e.to_dict() for e in reversed(events[-limit:])]
    
    def get_all_camera_status(self) -> Dict:
        """Get recovery status for all cameras"""
        with self.lock:
            return {
                camera_id: {
                    'camera_id': camera_id,
                    'error_count': self.camera_error_counts.get(camera_id, 0),
                    'recovery_count': self.camera_recovery_counts.get(camera_id, 0),
                    'last_error_time': self.camera_last_error_time.get(camera_id),
                    'is_healthy': self.camera_error_counts.get(camera_id, 0) == 0
                }
                for camera_id in self.camera_error_counts.keys()
            }

