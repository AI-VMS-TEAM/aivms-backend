"""
IOPS (Input/Output Operations Per Second) and throughput tracking service
Measures write performance and detects I/O bottlenecks
"""

import threading
import time
import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class IOPSSnapshot:
    """Snapshot of IOPS metrics at a point in time"""
    timestamp: float
    total_operations: int  # Total write operations since start
    operations_per_second: float  # Current IOPS
    total_bytes_written: int  # Total bytes written since start
    throughput_mbps: float  # Current throughput in MB/s
    avg_operation_size_bytes: float  # Average bytes per operation
    
    def to_dict(self):
        return {
            'timestamp': self.timestamp,
            'total_operations': self.total_operations,
            'operations_per_second': round(self.operations_per_second, 2),
            'total_bytes_written': self.total_bytes_written,
            'throughput_mbps': round(self.throughput_mbps, 2),
            'avg_operation_size_bytes': round(self.avg_operation_size_bytes, 2),
        }


class IOPSTracker:
    """
    Tracks write IOPS and throughput for the recording system.
    Monitors both file writes and database writes.
    """
    
    def __init__(self, history_size: int = 144):
        """
        Initialize IOPS tracker.
        
        Args:
            history_size: Number of snapshots to keep (144 = 24 hours at 10-min intervals)
        """
        self.history_size = history_size
        self.history = deque(maxlen=history_size)
        
        # Per-camera tracking
        self.camera_stats = {}  # camera_id -> {'operations': int, 'bytes': int}
        
        # Global stats
        self.total_operations = 0
        self.total_bytes_written = 0
        self.start_time = time.time()
        
        # Measurement window (for calculating current IOPS)
        self.window_start_time = time.time()
        self.window_operations = 0
        self.window_bytes = 0
        self.window_duration = 10.0  # 10-second window for IOPS calculation
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        logger.info("IOPSTracker initialized")
    
    def record_write(self, camera_id: str, num_bytes: int, operation_type: str = 'file'):
        """
        Record a write operation.
        
        Args:
            camera_id: Camera identifier
            num_bytes: Number of bytes written
            operation_type: Type of operation ('file' or 'database')
        """
        with self.lock:
            current_time = time.time()
            
            # Update global stats
            self.total_operations += 1
            self.total_bytes_written += num_bytes
            
            # Update window stats
            self.window_operations += 1
            self.window_bytes += num_bytes
            
            # Update per-camera stats
            if camera_id not in self.camera_stats:
                self.camera_stats[camera_id] = {'operations': 0, 'bytes': 0}
            self.camera_stats[camera_id]['operations'] += 1
            self.camera_stats[camera_id]['bytes'] += num_bytes
            
            # Check if window has expired
            if current_time - self.window_start_time >= self.window_duration:
                self._create_snapshot(current_time)
    
    def _create_snapshot(self, current_time: float):
        """Create a snapshot of current IOPS metrics."""
        elapsed = current_time - self.window_start_time
        
        if elapsed > 0:
            iops = self.window_operations / elapsed
            throughput_bytes = self.window_bytes / elapsed
            throughput_mbps = throughput_bytes / (1024 * 1024)
            
            if self.window_operations > 0:
                avg_size = self.window_bytes / self.window_operations
            else:
                avg_size = 0
            
            snapshot = IOPSSnapshot(
                timestamp=current_time,
                total_operations=self.total_operations,
                operations_per_second=iops,
                total_bytes_written=self.total_bytes_written,
                throughput_mbps=throughput_mbps,
                avg_operation_size_bytes=avg_size
            )
            
            self.history.append(snapshot)
            
            # Reset window
            self.window_start_time = current_time
            self.window_operations = 0
            self.window_bytes = 0
    
    def get_current_iops(self) -> IOPSSnapshot:
        """Get current IOPS metrics."""
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.window_start_time
            
            if elapsed > 0:
                iops = self.window_operations / elapsed
                throughput_bytes = self.window_bytes / elapsed
                throughput_mbps = throughput_bytes / (1024 * 1024)
                
                if self.window_operations > 0:
                    avg_size = self.window_bytes / self.window_operations
                else:
                    avg_size = 0
            else:
                iops = 0
                throughput_mbps = 0
                avg_size = 0
            
            return IOPSSnapshot(
                timestamp=current_time,
                total_operations=self.total_operations,
                operations_per_second=iops,
                total_bytes_written=self.total_bytes_written,
                throughput_mbps=throughput_mbps,
                avg_operation_size_bytes=avg_size
            )
    
    def get_camera_iops(self, camera_id: str) -> Dict:
        """Get IOPS stats for a specific camera."""
        with self.lock:
            if camera_id not in self.camera_stats:
                return {
                    'camera_id': camera_id,
                    'total_operations': 0,
                    'total_bytes': 0,
                    'percent_of_total_ops': 0.0,
                    'percent_of_total_bytes': 0.0,
                }
            
            stats = self.camera_stats[camera_id]
            
            percent_ops = (stats['operations'] / self.total_operations * 100) if self.total_operations > 0 else 0
            percent_bytes = (stats['bytes'] / self.total_bytes_written * 100) if self.total_bytes_written > 0 else 0
            
            return {
                'camera_id': camera_id,
                'total_operations': stats['operations'],
                'total_bytes': stats['bytes'],
                'total_mb': round(stats['bytes'] / (1024 * 1024), 2),
                'percent_of_total_ops': round(percent_ops, 2),
                'percent_of_total_bytes': round(percent_bytes, 2),
            }
    
    def get_all_camera_iops(self) -> List[Dict]:
        """Get IOPS stats for all cameras."""
        with self.lock:
            result = []
            for cam_id in self.camera_stats.keys():
                if cam_id not in self.camera_stats:
                    continue

                stats = self.camera_stats[cam_id]
                percent_ops = (stats['operations'] / self.total_operations * 100) if self.total_operations > 0 else 0
                percent_bytes = (stats['bytes'] / self.total_bytes_written * 100) if self.total_bytes_written > 0 else 0

                result.append({
                    'camera_id': cam_id,
                    'total_operations': stats['operations'],
                    'total_bytes': stats['bytes'],
                    'total_mb': round(stats['bytes'] / (1024 * 1024), 2),
                    'percent_of_total_ops': round(percent_ops, 2),
                    'percent_of_total_bytes': round(percent_bytes, 2),
                })
            return result
    
    def get_history(self, hours: int = 1) -> List[Dict]:
        """Get historical IOPS data."""
        with self.lock:
            # Each snapshot is roughly 10 minutes apart
            # So for 1 hour, we want ~6 snapshots
            snapshots_needed = max(1, int(hours * 6))
            
            history_list = list(self.history)
            if len(history_list) > snapshots_needed:
                history_list = history_list[-snapshots_needed:]
            
            return [s.to_dict() for s in history_list]
    
    def get_average_iops(self, hours: int = 1) -> Dict:
        """Get average IOPS over a time period."""
        with self.lock:
            if not self.history:
                return {
                    'period_hours': hours,
                    'avg_iops': 0.0,
                    'avg_throughput_mbps': 0.0,
                    'min_iops': 0.0,
                    'max_iops': 0.0,
                }
            
            snapshots = list(self.history)
            if not snapshots:
                return {
                    'period_hours': hours,
                    'avg_iops': 0.0,
                    'avg_throughput_mbps': 0.0,
                    'min_iops': 0.0,
                    'max_iops': 0.0,
                }
            
            iops_values = [s.operations_per_second for s in snapshots]
            throughput_values = [s.throughput_mbps for s in snapshots]
            
            return {
                'period_hours': hours,
                'avg_iops': round(sum(iops_values) / len(iops_values), 2),
                'avg_throughput_mbps': round(sum(throughput_values) / len(throughput_values), 2),
                'min_iops': round(min(iops_values), 2),
                'max_iops': round(max(iops_values), 2),
                'sample_count': len(snapshots),
            }

