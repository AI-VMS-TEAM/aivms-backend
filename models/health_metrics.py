"""
Health metrics data models for storage monitoring
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional
import json


@dataclass
class DiskUsageMetrics:
    """Disk usage metrics snapshot"""
    timestamp: float  # Unix timestamp
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent_used: float
    percent_free: float
    growth_rate_bytes_per_hour: float  # Calculated from history
    estimated_hours_until_full: Optional[float]  # Calculated
    
    def to_dict(self):
        return asdict(self)
    
    @property
    def total_gb(self):
        return self.total_bytes / (1024**3)
    
    @property
    def used_gb(self):
        return self.used_bytes / (1024**3)
    
    @property
    def free_gb(self):
        return self.free_bytes / (1024**3)


@dataclass
class CameraUsageMetrics:
    """Per-camera disk usage metrics"""
    camera_id: str
    camera_name: str
    timestamp: float
    total_bytes: int
    segment_count: int
    percent_of_total: float
    growth_rate_bytes_per_hour: float
    
    def to_dict(self):
        return asdict(self)
    
    @property
    def total_gb(self):
        return self.total_bytes / (1024**3)


@dataclass
class IOPSMetrics:
    """Write performance metrics"""
    timestamp: float
    total_iops: float  # Operations per second
    total_bytes_per_sec: float
    camera_iops: Dict[str, float]  # Per-camera IOPS
    camera_bytes_per_sec: Dict[str, float]  # Per-camera throughput
    
    def to_dict(self):
        data = asdict(self)
        return data


@dataclass
class SegmentValidationMetrics:
    """Segment integrity metrics"""
    timestamp: float
    total_segments: int
    valid_segments: int
    corrupted_segments: int
    percent_valid: float
    corrupted_files: List[str]  # List of corrupted file paths
    
    def to_dict(self):
        return asdict(self)


@dataclass
class HealthAlert:
    """Health alert event"""
    timestamp: float
    alert_type: str  # 'disk_usage', 'iops', 'corruption', 'performance'
    severity: str  # 'info', 'warning', 'critical'
    message: str
    camera_id: Optional[str] = None
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    
    def to_dict(self):
        return asdict(self)


@dataclass
class HealthStatus:
    """Overall system health status"""
    timestamp: float
    disk_status: str  # 'healthy', 'warning', 'critical'
    iops_status: str
    segment_status: str
    overall_status: str  # 'healthy', 'warning', 'critical'
    
    disk_metrics: Optional[DiskUsageMetrics] = None
    camera_metrics: Optional[List[CameraUsageMetrics]] = None
    iops_metrics: Optional[IOPSMetrics] = None
    segment_metrics: Optional[SegmentValidationMetrics] = None
    active_alerts: Optional[List[HealthAlert]] = None
    
    def to_dict(self):
        data = {
            'timestamp': self.timestamp,
            'disk_status': self.disk_status,
            'iops_status': self.iops_status,
            'segment_status': self.segment_status,
            'overall_status': self.overall_status,
        }
        
        if self.disk_metrics:
            data['disk_metrics'] = self.disk_metrics.to_dict()
        if self.camera_metrics:
            data['camera_metrics'] = [m.to_dict() for m in self.camera_metrics]
        if self.iops_metrics:
            data['iops_metrics'] = self.iops_metrics.to_dict()
        if self.segment_metrics:
            data['segment_metrics'] = self.segment_metrics.to_dict()
        if self.active_alerts:
            data['active_alerts'] = [a.to_dict() for a in self.active_alerts]
        
        return data


# Alert thresholds
ALERT_THRESHOLDS = {
    'disk_usage': {
        'warning': 70,      # 70% disk usage
        'critical': 85,     # 85% disk usage
    },
    'iops': {
        'warning': 500,     # 500 ops/sec
        'critical': 250,    # 250 ops/sec
    },
    'segment_validity': {
        'warning': 99.0,    # 99% valid
        'critical': 98.0,   # 98% valid
    },
}

