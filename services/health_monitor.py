"""
Health monitoring service
Orchestrates all health monitoring components
"""

import threading
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
from collections import deque

from services.disk_usage_tracker import DiskUsageTracker
from services.iops_tracker import IOPSTracker
from models.health_metrics import (
    DiskUsageMetrics, CameraUsageMetrics, IOPSMetrics,
    HealthAlert, HealthStatus, ALERT_THRESHOLDS
)

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    Main health monitoring service
    Tracks disk usage, performance, and system health
    """
    
    def __init__(self, storage_path: str, camera_ids: List[str], check_interval_seconds: int = 60):
        """
        Initialize health monitor
        
        Args:
            storage_path: Path to recordings directory
            camera_ids: List of camera identifiers
            check_interval_seconds: How often to check health (default 60 seconds)
        """
        self.storage_path = storage_path
        self.camera_ids = camera_ids
        self.check_interval_seconds = check_interval_seconds
        
        # Initialize components
        self.disk_tracker = DiskUsageTracker(storage_path)
        self.iops_tracker = IOPSTracker()

        # State
        self.is_running = False
        self.monitor_thread = None
        self.recording_engine = None  # Set by app.py after initialization

        # Metrics history
        self.disk_metrics_history = deque(maxlen=144)  # 24 hours at 10-min intervals
        self.camera_metrics_history = {}  # camera_id -> deque of metrics
        self.iops_metrics_history = deque(maxlen=144)
        self.alerts_history = deque(maxlen=1000)
        
        # Current state
        self.current_health_status = None
        self.active_alerts = []
        
        logger.info(f"HealthMonitor initialized for {len(camera_ids)} cameras")
    
    def start(self):
        """Start health monitoring thread"""
        if self.is_running:
            logger.warning("Health monitor already running")
            return

        self.is_running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="HealthMonitorThread"
        )
        self.monitor_thread.start()

        logger.info("Health monitor started")
    
    def stop(self):
        """Stop health monitoring thread"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

        logger.info("Health monitor stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_running:
            try:
                self._check_health()
                time.sleep(self.check_interval_seconds)
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}")
                time.sleep(self.check_interval_seconds)
    
    def _check_health(self):
        """Check system health and update status"""
        try:
            # Get disk metrics
            disk_metrics = self.disk_tracker.get_disk_metrics()
            self.disk_metrics_history.append(disk_metrics)
            
            # Get per-camera metrics
            camera_metrics = self.disk_tracker.get_all_camera_usage(self.camera_ids)
            for camera_id, metrics in camera_metrics.items():
                if camera_id not in self.camera_metrics_history:
                    self.camera_metrics_history[camera_id] = deque(maxlen=144)
                self.camera_metrics_history[camera_id].append(metrics)
            
            # Check thresholds and generate alerts
            self._check_disk_thresholds(disk_metrics)
            
            # Update overall health status
            self._update_health_status(disk_metrics, camera_metrics)
            
        except Exception as e:
            logger.error(f"Error checking health: {e}")
    
    def _check_disk_thresholds(self, disk_metrics: DiskUsageMetrics):
        """Check disk usage thresholds and generate alerts"""
        percent_used = disk_metrics.percent_used
        
        # Check for critical threshold
        if percent_used >= ALERT_THRESHOLDS['disk_usage']['critical']:
            self._create_alert(
                alert_type='disk_usage',
                severity='critical',
                message=f"Disk usage critical: {percent_used:.1f}% used",
                metric_value=percent_used,
                threshold=ALERT_THRESHOLDS['disk_usage']['critical'],
            )
        # Check for warning threshold
        elif percent_used >= ALERT_THRESHOLDS['disk_usage']['warning']:
            self._create_alert(
                alert_type='disk_usage',
                severity='warning',
                message=f"Disk usage warning: {percent_used:.1f}% used",
                metric_value=percent_used,
                threshold=ALERT_THRESHOLDS['disk_usage']['warning'],
            )
    
    def _create_alert(self, alert_type: str, severity: str, message: str,
                     metric_value: Optional[float] = None,
                     threshold: Optional[float] = None,
                     camera_id: Optional[str] = None):
        """Create and store an alert"""
        alert = HealthAlert(
            timestamp=datetime.now().timestamp(),
            alert_type=alert_type,
            severity=severity,
            message=message,
            camera_id=camera_id,
            metric_value=metric_value,
            threshold=threshold,
        )
        
        self.alerts_history.append(alert)
        
        # Update active alerts
        if severity in ['warning', 'critical']:
            self.active_alerts.append(alert)
            # Keep only recent alerts
            self.active_alerts = self.active_alerts[-100:]
        
        logger.warning(f"[{severity.upper()}] {message}")
    
    def _update_health_status(self, disk_metrics: DiskUsageMetrics,
                             camera_metrics: Dict[str, CameraUsageMetrics]):
        """Update overall health status"""
        # Determine disk status
        if disk_metrics.percent_used >= ALERT_THRESHOLDS['disk_usage']['critical']:
            disk_status = 'critical'
        elif disk_metrics.percent_used >= ALERT_THRESHOLDS['disk_usage']['warning']:
            disk_status = 'warning'
        else:
            disk_status = 'healthy'
        
        # Overall status is worst of all components
        overall_status = disk_status  # For now, just disk status
        
        self.current_health_status = HealthStatus(
            timestamp=datetime.now().timestamp(),
            disk_status=disk_status,
            iops_status='healthy',  # Will be updated in Phase 2
            segment_status='healthy',  # Will be updated in Phase 3
            overall_status=overall_status,
            disk_metrics=disk_metrics,
            camera_metrics=list(camera_metrics.values()),
            active_alerts=self.active_alerts[-10:],  # Last 10 alerts
        )
    
    def get_health_status(self) -> Optional[HealthStatus]:
        """Get current health status"""
        return self.current_health_status
    
    def get_disk_metrics(self) -> Optional[DiskUsageMetrics]:
        """Get current disk metrics"""
        if self.disk_metrics_history:
            return self.disk_metrics_history[-1]
        return None
    
    def get_camera_metrics(self, camera_id: str) -> Optional[List[CameraUsageMetrics]]:
        """Get metrics history for a camera"""
        if camera_id in self.camera_metrics_history:
            return list(self.camera_metrics_history[camera_id])
        return None
    
    def get_alerts(self, limit: int = 100) -> List[HealthAlert]:
        """Get recent alerts"""
        return list(self.alerts_history)[-limit:]
    
    def get_metrics_history(self, hours: int = 24) -> Dict:
        """Get historical metrics for the last N hours"""
        return {
            'disk_metrics': list(self.disk_metrics_history),
            'camera_metrics': {
                camera_id: list(metrics)
                for camera_id, metrics in self.camera_metrics_history.items()
            },
            'alerts': list(self.alerts_history),
        }

    def get_iops_metrics(self) -> Dict:
        """Get current IOPS metrics"""
        current_iops = self.iops_tracker.get_current_iops()
        return {
            'current': current_iops.to_dict(),
            'by_camera': self.iops_tracker.get_all_camera_iops(),
            'average_1h': self.iops_tracker.get_average_iops(hours=1),
            'average_24h': self.iops_tracker.get_average_iops(hours=24),
        }

    def record_write_operation(self, camera_id: str, num_bytes: int):
        """Record a write operation for IOPS tracking"""
        self.iops_tracker.record_write(camera_id, num_bytes, operation_type='file')

