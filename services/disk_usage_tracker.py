"""
Disk usage tracking service
Monitors disk space usage and per-camera storage
"""

import os
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from collections import deque

from models.health_metrics import DiskUsageMetrics, CameraUsageMetrics

logger = logging.getLogger(__name__)


class DiskUsageTracker:
    """
    Tracks disk usage and calculates growth rates
    """
    
    def __init__(self, storage_path: str, history_size: int = 144):
        """
        Initialize disk usage tracker
        
        Args:
            storage_path: Path to recordings directory
            history_size: Number of historical samples to keep (144 = 24 hours at 10-min intervals)
        """
        self.storage_path = Path(storage_path)
        self.history_size = history_size
        
        # Keep history of disk usage for growth rate calculation
        self.usage_history = deque(maxlen=history_size)
        
        logger.info(f"DiskUsageTracker initialized for {storage_path}")
    
    def get_disk_metrics(self) -> DiskUsageMetrics:
        """
        Get current disk usage metrics
        
        Returns:
            DiskUsageMetrics object with current disk state
        """
        try:
            stat = shutil.disk_usage(str(self.storage_path))
            
            timestamp = datetime.now().timestamp()
            total_bytes = stat.total
            used_bytes = stat.used
            free_bytes = stat.free
            
            percent_used = (used_bytes / total_bytes * 100) if total_bytes > 0 else 0
            percent_free = (free_bytes / total_bytes * 100) if total_bytes > 0 else 0
            
            # Calculate growth rate from history
            growth_rate = self._calculate_growth_rate(used_bytes)
            
            # Estimate time until full
            hours_until_full = self._estimate_hours_until_full(
                free_bytes, growth_rate
            )
            
            metrics = DiskUsageMetrics(
                timestamp=timestamp,
                total_bytes=total_bytes,
                used_bytes=used_bytes,
                free_bytes=free_bytes,
                percent_used=percent_used,
                percent_free=percent_free,
                growth_rate_bytes_per_hour=growth_rate,
                estimated_hours_until_full=hours_until_full,
            )
            
            # Add to history
            self.usage_history.append((timestamp, used_bytes))
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting disk metrics: {e}")
            raise
    
    def get_camera_usage(self, camera_id: str, camera_name: str) -> CameraUsageMetrics:
        """
        Get disk usage for a specific camera
        
        Args:
            camera_id: Camera identifier
            camera_name: Camera display name
            
        Returns:
            CameraUsageMetrics object
        """
        try:
            camera_path = self.storage_path / camera_id
            
            if not camera_path.exists():
                return CameraUsageMetrics(
                    camera_id=camera_id,
                    camera_name=camera_name,
                    timestamp=datetime.now().timestamp(),
                    total_bytes=0,
                    segment_count=0,
                    percent_of_total=0.0,
                    growth_rate_bytes_per_hour=0.0,
                )
            
            # Calculate total size
            total_bytes = sum(
                f.stat().st_size for f in camera_path.rglob('*') if f.is_file()
            )
            
            # Count segments
            segment_count = len(list(camera_path.rglob('*.mp4')))
            
            # Get total disk usage for percentage
            disk_metrics = self.get_disk_metrics()
            percent_of_total = (
                (total_bytes / disk_metrics.used_bytes * 100)
                if disk_metrics.used_bytes > 0 else 0
            )
            
            # Calculate growth rate for this camera
            growth_rate = self._calculate_camera_growth_rate(camera_id, total_bytes)
            
            return CameraUsageMetrics(
                camera_id=camera_id,
                camera_name=camera_name,
                timestamp=datetime.now().timestamp(),
                total_bytes=total_bytes,
                segment_count=segment_count,
                percent_of_total=percent_of_total,
                growth_rate_bytes_per_hour=growth_rate,
            )
            
        except Exception as e:
            logger.error(f"Error getting camera usage for {camera_id}: {e}")
            raise
    
    def get_all_camera_usage(self, camera_ids: List[str]) -> Dict[str, CameraUsageMetrics]:
        """
        Get disk usage for all cameras
        
        Args:
            camera_ids: List of camera identifiers
            
        Returns:
            Dictionary mapping camera_id to CameraUsageMetrics
        """
        result = {}
        for camera_id in camera_ids:
            # Extract camera name from ID (e.g., 'wisenet_front' -> 'Wisenet Front')
            camera_name = camera_id.replace('_', ' ').title()
            result[camera_id] = self.get_camera_usage(camera_id, camera_name)
        return result
    
    def _calculate_growth_rate(self, current_used_bytes: int) -> float:
        """
        Calculate disk usage growth rate in bytes per hour
        
        Args:
            current_used_bytes: Current used bytes
            
        Returns:
            Growth rate in bytes per hour
        """
        if len(self.usage_history) < 2:
            return 0.0
        
        try:
            oldest_time, oldest_bytes = self.usage_history[0]
            newest_time, newest_bytes = self.usage_history[-1]
            
            time_diff_hours = (newest_time - oldest_time) / 3600
            bytes_diff = newest_bytes - oldest_bytes
            
            if time_diff_hours > 0:
                return bytes_diff / time_diff_hours
            return 0.0
            
        except Exception as e:
            logger.warning(f"Error calculating growth rate: {e}")
            return 0.0
    
    def _calculate_camera_growth_rate(
        self, camera_id: str, current_bytes: int
    ) -> float:
        """
        Calculate per-camera growth rate (simplified - based on current rate)
        
        Args:
            camera_id: Camera identifier
            current_bytes: Current bytes for camera
            
        Returns:
            Growth rate in bytes per hour
        """
        # For now, estimate based on total growth rate and camera percentage
        total_metrics = self.get_disk_metrics()
        if total_metrics.used_bytes > 0:
            camera_percent = current_bytes / total_metrics.used_bytes
            return total_metrics.growth_rate_bytes_per_hour * camera_percent
        return 0.0
    
    def _estimate_hours_until_full(
        self, free_bytes: int, growth_rate_bytes_per_hour: float
    ) -> Optional[float]:
        """
        Estimate hours until disk is full
        
        Args:
            free_bytes: Free bytes available
            growth_rate_bytes_per_hour: Growth rate in bytes per hour
            
        Returns:
            Hours until full, or None if growth rate is 0 or negative
        """
        if growth_rate_bytes_per_hour <= 0:
            return None
        
        hours = free_bytes / growth_rate_bytes_per_hour
        return max(0, hours)

