"""
Event Service
Stores and retrieves detection events, zone events, and clips from edge devices.
"""

import os
import sqlite3
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class EventService:
    """
    Manages events from edge devices.
    - Detection events (objects detected)
    - Zone events (enter/exit/dwell)
    - Clip metadata
    - Event queries and filtering
    """
    
    def __init__(self, db_path: str = './cloud.db'):
        self.db_path = db_path
        self._init_database()
        logger.info("✅ Event service initialized")
    
    @contextmanager
    def _get_db(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialize database schema."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            # Detection events table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS detection_events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    edge_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    object_class TEXT NOT NULL,
                    confidence REAL,
                    track_id TEXT,
                    bbox TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Zone events table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS zone_events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    edge_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    zone_id TEXT NOT NULL,
                    zone_name TEXT,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    object_class TEXT,
                    track_id TEXT,
                    dwell_time REAL,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Clips table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS event_clips (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    edge_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_id TEXT,
                    timestamp TEXT NOT NULL,
                    duration REAL,
                    file_path TEXT,
                    file_size INTEGER,
                    thumbnail_path TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Alerts table (processed/filtered events)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    edge_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT DEFAULT 'info',
                    title TEXT NOT NULL,
                    description TEXT,
                    event_id TEXT,
                    clip_id TEXT,
                    timestamp TEXT NOT NULL,
                    acknowledged INTEGER DEFAULT 0,
                    acknowledged_by TEXT,
                    acknowledged_at TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Create indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_detection_tenant ON detection_events(tenant_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_detection_edge ON detection_events(edge_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_detection_timestamp ON detection_events(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_zone_tenant ON zone_events(tenant_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_zone_edge ON zone_events(edge_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_zone_timestamp ON zone_events(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_tenant ON alerts(tenant_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)')
            
            logger.info("✅ Event database schema initialized")
    
    # ==========================================
    # Detection Events
    # ==========================================
    
    def store_detection(self, event_data: Dict) -> Optional[str]:
        """Store a detection event from edge."""
        import secrets
        event_id = f"det_{secrets.token_hex(8)}"
        now = datetime.now().isoformat()
        
        try:
            with self._get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO detection_events 
                    (id, tenant_id, edge_id, camera_id, timestamp, object_class, 
                     confidence, track_id, bbox, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    event_id,
                    event_data.get('tenant_id'),
                    event_data.get('edge_id'),
                    event_data.get('camera_id'),
                    event_data.get('timestamp', now),
                    event_data.get('object_class'),
                    event_data.get('confidence'),
                    event_data.get('track_id'),
                    json.dumps(event_data.get('bbox')) if event_data.get('bbox') else None,
                    json.dumps(event_data.get('metadata')) if event_data.get('metadata') else None,
                    now
                ))
            return event_id
        except Exception as e:
            logger.error(f"Failed to store detection: {e}")
            return None
    
    def get_detections(
        self,
        tenant_id: str,
        edge_id: str = None,
        camera_id: str = None,
        object_class: str = None,
        start_time: str = None,
        end_time: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """Query detection events."""
        query = 'SELECT * FROM detection_events WHERE tenant_id = ?'
        params = [tenant_id]
        
        if edge_id:
            query += ' AND edge_id = ?'
            params.append(edge_id)
        if camera_id:
            query += ' AND camera_id = ?'
            params.append(camera_id)
        if object_class:
            query += ' AND object_class = ?'
            params.append(object_class)
        if start_time:
            query += ' AND timestamp >= ?'
            params.append(start_time)
        if end_time:
            query += ' AND timestamp <= ?'
            params.append(end_time)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = []
            for row in cursor.fetchall():
                event = dict(row)
                if event.get('bbox'):
                    event['bbox'] = json.loads(event['bbox'])
                if event.get('metadata'):
                    event['metadata'] = json.loads(event['metadata'])
                results.append(event)
            return results
    
    # ==========================================
    # Zone Events
    # ==========================================
    
    def store_zone_event(self, event_data: Dict) -> Optional[str]:
        """Store a zone event from edge."""
        import secrets
        event_id = f"zone_{secrets.token_hex(8)}"
        now = datetime.now().isoformat()
        
        try:
            with self._get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO zone_events 
                    (id, tenant_id, edge_id, camera_id, zone_id, zone_name, event_type,
                     timestamp, object_class, track_id, dwell_time, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    event_id,
                    event_data.get('tenant_id'),
                    event_data.get('edge_id'),
                    event_data.get('camera_id'),
                    event_data.get('zone_id'),
                    event_data.get('zone_name'),
                    event_data.get('event_type'),
                    event_data.get('timestamp', now),
                    event_data.get('object_class'),
                    event_data.get('track_id'),
                    event_data.get('dwell_time'),
                    json.dumps(event_data.get('metadata')) if event_data.get('metadata') else None,
                    now
                ))
            return event_id
        except Exception as e:
            logger.error(f"Failed to store zone event: {e}")
            return None
    
    def get_zone_events(
        self,
        tenant_id: str,
        edge_id: str = None,
        zone_id: str = None,
        event_type: str = None,
        start_time: str = None,
        end_time: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """Query zone events."""
        query = 'SELECT * FROM zone_events WHERE tenant_id = ?'
        params = [tenant_id]
        
        if edge_id:
            query += ' AND edge_id = ?'
            params.append(edge_id)
        if zone_id:
            query += ' AND zone_id = ?'
            params.append(zone_id)
        if event_type:
            query += ' AND event_type = ?'
            params.append(event_type)
        if start_time:
            query += ' AND timestamp >= ?'
            params.append(start_time)
        if end_time:
            query += ' AND timestamp <= ?'
            params.append(end_time)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = []
            for row in cursor.fetchall():
                event = dict(row)
                if event.get('metadata'):
                    event['metadata'] = json.loads(event['metadata'])
                results.append(event)
            return results
    
    # ==========================================
    # Clips
    # ==========================================
    
    def store_clip_metadata(self, clip_data: Dict) -> Optional[str]:
        """Store clip metadata."""
        import secrets
        clip_id = f"clip_{secrets.token_hex(8)}"
        now = datetime.now().isoformat()
        
        try:
            with self._get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO event_clips 
                    (id, tenant_id, edge_id, camera_id, event_type, event_id,
                     timestamp, duration, file_path, file_size, thumbnail_path, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    clip_id,
                    clip_data.get('tenant_id'),
                    clip_data.get('edge_id'),
                    clip_data.get('camera_id'),
                    clip_data.get('event_type'),
                    clip_data.get('event_id'),
                    clip_data.get('timestamp', now),
                    clip_data.get('duration'),
                    clip_data.get('file_path'),
                    clip_data.get('file_size'),
                    clip_data.get('thumbnail_path'),
                    json.dumps(clip_data.get('metadata')) if clip_data.get('metadata') else None,
                    now
                ))
            return clip_id
        except Exception as e:
            logger.error(f"Failed to store clip metadata: {e}")
            return None
    
    def get_clips(
        self,
        tenant_id: str,
        edge_id: str = None,
        camera_id: str = None,
        event_type: str = None,
        start_time: str = None,
        end_time: str = None,
        limit: int = 50
    ) -> List[Dict]:
        """Query clips."""
        query = 'SELECT * FROM event_clips WHERE tenant_id = ?'
        params = [tenant_id]
        
        if edge_id:
            query += ' AND edge_id = ?'
            params.append(edge_id)
        if camera_id:
            query += ' AND camera_id = ?'
            params.append(camera_id)
        if event_type:
            query += ' AND event_type = ?'
            params.append(event_type)
        if start_time:
            query += ' AND timestamp >= ?'
            params.append(start_time)
        if end_time:
            query += ' AND timestamp <= ?'
            params.append(end_time)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = []
            for row in cursor.fetchall():
                clip = dict(row)
                if clip.get('metadata'):
                    clip['metadata'] = json.loads(clip['metadata'])
                results.append(clip)
            return results
    
    # ==========================================
    # Alerts
    # ==========================================
    
    def create_alert(self, alert_data: Dict) -> Optional[str]:
        """Create an alert."""
        import secrets
        alert_id = f"alert_{secrets.token_hex(8)}"
        now = datetime.now().isoformat()
        
        try:
            with self._get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO alerts 
                    (id, tenant_id, edge_id, camera_id, alert_type, severity, title,
                     description, event_id, clip_id, timestamp, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    alert_id,
                    alert_data.get('tenant_id'),
                    alert_data.get('edge_id'),
                    alert_data.get('camera_id'),
                    alert_data.get('alert_type'),
                    alert_data.get('severity', 'info'),
                    alert_data.get('title'),
                    alert_data.get('description'),
                    alert_data.get('event_id'),
                    alert_data.get('clip_id'),
                    alert_data.get('timestamp', now),
                    json.dumps(alert_data.get('metadata')) if alert_data.get('metadata') else None,
                    now
                ))
            return alert_id
        except Exception as e:
            logger.error(f"Failed to create alert: {e}")
            return None
    
    def get_alerts(
        self,
        tenant_id: str,
        edge_id: str = None,
        alert_type: str = None,
        severity: str = None,
        acknowledged: bool = None,
        start_time: str = None,
        end_time: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """Query alerts."""
        query = 'SELECT * FROM alerts WHERE tenant_id = ?'
        params = [tenant_id]
        
        if edge_id:
            query += ' AND edge_id = ?'
            params.append(edge_id)
        if alert_type:
            query += ' AND alert_type = ?'
            params.append(alert_type)
        if severity:
            query += ' AND severity = ?'
            params.append(severity)
        if acknowledged is not None:
            query += ' AND acknowledged = ?'
            params.append(1 if acknowledged else 0)
        if start_time:
            query += ' AND timestamp >= ?'
            params.append(start_time)
        if end_time:
            query += ' AND timestamp <= ?'
            params.append(end_time)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = []
            for row in cursor.fetchall():
                alert = dict(row)
                if alert.get('metadata'):
                    alert['metadata'] = json.loads(alert['metadata'])
                results.append(alert)
            return results
    
    def acknowledge_alert(self, alert_id: str, user_id: str) -> bool:
        """Acknowledge an alert."""
        now = datetime.now().isoformat()
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE alerts SET acknowledged = 1, acknowledged_by = ?, acknowledged_at = ?
                WHERE id = ?
            ''', (user_id, now, alert_id))
            return cursor.rowcount > 0
    
    def get_unacknowledged_count(self, tenant_id: str) -> int:
        """Get count of unacknowledged alerts."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM alerts WHERE tenant_id = ? AND acknowledged = 0
            ''', (tenant_id,))
            return cursor.fetchone()[0]
    
    # ==========================================
    # Analytics
    # ==========================================
    
    def get_detection_counts(
        self,
        tenant_id: str,
        start_time: str,
        end_time: str,
        group_by: str = 'hour'
    ) -> List[Dict]:
        """Get detection counts grouped by time."""
        if group_by == 'hour':
            time_format = '%Y-%m-%d %H:00:00'
        elif group_by == 'day':
            time_format = '%Y-%m-%d'
        else:
            time_format = '%Y-%m-%d %H:00:00'
        
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
                SELECT strftime('{time_format}', timestamp) as period,
                       object_class,
                       COUNT(*) as count
                FROM detection_events
                WHERE tenant_id = ? AND timestamp >= ? AND timestamp <= ?
                GROUP BY period, object_class
                ORDER BY period
            ''', (tenant_id, start_time, end_time))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_zone_activity(
        self,
        tenant_id: str,
        start_time: str,
        end_time: str
    ) -> List[Dict]:
        """Get zone activity summary."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT zone_id, zone_name, event_type, COUNT(*) as count,
                       AVG(dwell_time) as avg_dwell_time
                FROM zone_events
                WHERE tenant_id = ? AND timestamp >= ? AND timestamp <= ?
                GROUP BY zone_id, zone_name, event_type
                ORDER BY count DESC
            ''', (tenant_id, start_time, end_time))
            return [dict(row) for row in cursor.fetchall()]
    
    def cleanup_old_events(self, days: int = 30) -> Dict[str, int]:
        """Clean up events older than specified days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        counts = {}
        
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            # Delete old detections
            cursor.execute('DELETE FROM detection_events WHERE timestamp < ?', (cutoff,))
            counts['detections'] = cursor.rowcount
            
            # Delete old zone events
            cursor.execute('DELETE FROM zone_events WHERE timestamp < ?', (cutoff,))
            counts['zone_events'] = cursor.rowcount
            
            # Delete old acknowledged alerts
            cursor.execute('''
                DELETE FROM alerts WHERE timestamp < ? AND acknowledged = 1
            ''', (cutoff,))
            counts['alerts'] = cursor.rowcount
        
        logger.info(f"🧹 Cleaned up old events: {counts}")
        return counts
